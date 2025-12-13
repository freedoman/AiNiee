import zipfile
import re
import tempfile
import shutil
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, PageElement, Tag
from datetime import datetime

from ModuleFolders.FileAccessor import ZipUtil


class DocxAccessor:

    def __init__(self, simplify_options: dict | None = None):
        # 默认选项：简化模式 conservative(保守)/balanced(平衡)/aggressive(激进)
        self.simplify_options = {
            "remove_colors": True,
            "strip_spacing": "all",  # 'none' | 'zeros' | 'all'
            "strip_char_width": "all",  # 'none' | 'default' | 'all'
            "enable_diff_log": True,
            "backup_before_simplify": True,  # 简化前自动备份源文件
            "protect_vertalign": True,  # 保护上标/下标 run 不被合并
            "simplify_mode": "aggressive",  # conservative | balanced | aggressive
            "merge_mode": True,  # 启用合并段落模式
            "mark_italic_as_red": True,  # 将斜体文本标记为红色（便于识别强调内容）
            **(simplify_options or {})
        }

    def _preprocess_xml_content(self, content: str, source_file_path: Path | None = None, force_baseline: bool = False) -> str:
        """预处理 XML 内容：简化冗余标签 + 格式标准化"""
        if force_baseline:
            return self._apply_baseline_simplify(content)
        
        mode = self.simplify_options.get("simplify_mode", "balanced")
        
        # 步骤1: 基础清理（所有模式）
        content = self._remove_redundant_colors(content)
        content = self._deduplicate_font_sizes(content)
        content = self._remove_char_width_attributes(content)
        content = self._remove_empty_format_blocks(content)
        
        # 步骤2: 清理间距属性（仅 aggressive 模式）
        if mode == "aggressive":
            content = self._remove_spacing_attributes(content)
        
        # 步骤3: 合并相同格式的 runs（conservative 模式跳过）
        if mode != "conservative":
            content = self._merge_format_runs(content)
        
        # 步骤4: 合并连续空格（所有模式安全）
        content = self._merge_consecutive_spaces(content)
        
        # 步骤5: 将斜体文本标记为红色（便于识别强调内容）
        if self.simplify_options.get("mark_italic_as_red", True):
            content = self._mark_italic_runs_red(content)
        
        return content
    
    def _apply_baseline_simplify(self, content: str) -> str:
        """基线简化：仅去重字体大小（用于诊断对比）"""
        return self._deduplicate_font_sizes(content)
    
    def _remove_redundant_colors(self, content: str) -> str:
        """移除黑色/自动颜色（可配置）"""
        if self.simplify_options.get("remove_colors", True):
            return re.sub(r'<w:color w:val="(000000|auto)"\s*/?>', '', content, flags=re.IGNORECASE)
        return content
    
    def _deduplicate_font_sizes(self, content: str) -> str:
        """去重相同的 sz 和 szCs 标签"""
        return re.sub(
            r'<w:sz w:val="(\d+)"/><w:szCs w:val="\1"/>',
            r'<w:sz w:val="\1"/>',
            content
        )
    
    def _remove_empty_format_blocks(self, content: str) -> str:
        """删除空的 rPr 格式块"""
        return re.sub(r'<w:rPr>\s*</w:rPr>', '', content)
    
    def _remove_char_width_attributes(self, content: str) -> str:
        """清理字符宽度属性（w:w），提高 run 合并率
        
        w:w 控制字符宽度缩放：
        - 100 = 默认宽度（100%）
        - <100 = 压缩字符
        - >100 = 拉伸字符
        
        根据 strip_char_width 配置：
        - 'all': 删除所有 w:w 标签（aggressive 模式，最大合并率）
        - 'default': 仅删除 w:w=100 的标签（推荐，低风险）
        - 'none': 不删除任何 w:w（保留原始宽度）
        """
        strip_width = self.simplify_options.get("strip_char_width", "default")
        if strip_width == "none":
            return content
        
        # 使用正则表达式直接处理，避免 BeautifulSoup 序列化问题
        if strip_width == "all":
            # 删除所有 w:w 标签
            return re.sub(r'<w:w[^>]*?/>', '', content)
        elif strip_width == "default":
            # 仅删除 w:w=100 的标签
            return re.sub(r'<w:w\s+w:val="100"\s*/>', '', content)
    
    def _remove_spacing_attributes(self, content: str, mode: str = None) -> str:
        """清理 spacing 属性
        
        参数:
            content: XML 内容
            mode: 清理模式（覆盖配置）
                - 'all': 删除所有 run 级别的 w:spacing 标签
                - 'zeros': 仅删除 spacing=0 的标签（默认）
                - 'none': 不删除任何 spacing
        """
        strip_spacing = mode if mode is not None else self.simplify_options.get("strip_spacing", "zeros")
        if strip_spacing == "none":
            return content
        
        # 使用正则表达式处理 run 级别的 spacing（更可靠）
        # run 级别的 spacing 只有 w:val 属性，段落级别的有 w:before/w:line 等
        if strip_spacing == "all":
            # 删除所有只包含 w:val 的 spacing（run 级别）
            return re.sub(r'<w:spacing\s+w:val="[^"]*"\s*/>', '', content)
        else:  # zeros
            # 仅删除 w:val="0" 的 spacing
            return re.sub(r'<w:spacing\s+w:val="0"\s*/>', '', content)
    
    def _merge_format_runs(self, content: str) -> str:
        """迭代合并相邻的相同格式 runs
        
        每次迭代只能合并相邻的两个 runs，因此需要多次迭代。
        例如 4 个连续相同格式的 runs 需要 3 次迭代才能全部合并。
        设置上限防止异常情况下的无限循环。
        """
        MAX_ITERATIONS = 50  # 理论上足够处理任意长度的连续 runs
        
        for iteration in range(MAX_ITERATIONS):
            new_content = self._merge_adjacent_format_runs(content)
            if new_content == content:
                # 无变化，提前退出
                break
            content = new_content
        
        return content
    
    def _merge_consecutive_spaces(self, content: str) -> str:
        """合并连续的空格 runs"""
        return re.sub(
            r'(<w:r><w:t xml:space="preserve"> </w:t></w:r>){2,}',
            '<w:r><w:t xml:space="preserve"> </w:t></w:r>',
            content
        )

    def _mark_italic_runs_red(self, content: str) -> str:
        """将包含斜体标记的 run 文本设置为红色（保留斜体标记）
        
        这样做的目的：
        1. 保留原文中的强调信息（斜体通常用于强调）
        2. 叠加红色标记，使斜体内容更醒目
        3. 便于译者识别需要特别注意的强调内容
        """
        soup = BeautifulSoup(content, 'xml')
        modified = False
        
        for run in soup.find_all('w:r'):
            rpr = run.find('w:rPr')
            if not rpr:
                continue
            
            # 检查是否有斜体标记（w:i 或 w:iCs）
            italic = rpr.find('w:i')
            italic_cs = rpr.find('w:iCs')  # 复杂字体斜体
            
            if italic or italic_cs:
                # 添加或修改颜色为红色（保留斜体标记）
                color = rpr.find('w:color')
                if color:
                    color['w:val'] = 'FF0000'
                else:
                    # 创建新的颜色标签并插入到 rPr 开头
                    color_tag = soup.new_tag('w:color')
                    color_tag['w:val'] = 'FF0000'
                    rpr.insert(0, color_tag)
                
                modified = True
        
        return str(soup) if modified else content

    def _is_italic_marked_run(self, t_tag: Tag) -> bool:
        """检查 w:t 标签所在的 run 是否为红色斜体（已标记为不翻译内容）
        
        Returns:
            bool - True 表示该 run 包含斜体标记和红色，应该保持不翻译
        """
        run = t_tag.find_parent('w:r')
        if not run:
            return False
        
        rpr = run.find('w:rPr')
        if not rpr:
            return False
        
        # 检查是否有斜体标记
        has_italic = rpr.find('w:i') is not None or rpr.find('w:iCs') is not None
        
        # 检查是否为红色
        color = rpr.find('w:color')
        is_red = color is not None and color.get('w:val', '').upper() == 'FF0000'
        
        return has_italic and is_red

    def _merge_adjacent_format_runs(self, content: str) -> str:
        """合并相邻的相同格式 run（保护上标/下标和空格）"""
        pattern = r'(<w:r><w:rPr>([^<]*(?:<w:[^/>]+/>[^<]*)*?)</w:rPr><w:t[^>]*>([^<]*?)</w:t></w:r>)(\s*)(<w:r><w:rPr>\2</w:rPr><w:t[^>]*>([^<]*?)</w:t></w:r>)'
        
        def should_merge(format_str: str, spacing: str) -> bool:
            """判断是否应该合并"""
            # 保护上标/下标格式
            if self.simplify_options.get("protect_vertalign", True):
                if "vertAlign" in format_str or "position" in format_str:
                    return False
            # 保留有实际空白的间隔
            if spacing and spacing.strip():
                return False
            return True
        
        def replacer(m):
            if should_merge(m.group(2) or '', m.group(4)):
                # 合并文本
                merged_text = m.group(3) + m.group(6)
                # 如果合并后的文本包含首尾空格，需要添加 xml:space="preserve"
                if merged_text and (merged_text[0] == ' ' or merged_text[-1] == ' '):
                    return f'<w:r><w:rPr>{m.group(2)}</w:rPr><w:t xml:space="preserve">{merged_text}</w:t></w:r>'
                else:
                    return f'<w:r><w:rPr>{m.group(2)}</w:rPr><w:t>{merged_text}</w:t></w:r>'
            return m.group(0)
        
        return re.sub(pattern, replacer, content, flags=re.DOTALL)

    def _read_xml_from_docx(self, source_file_path: Path, xml_name: str) -> str | None:
        """从 DOCX 文件读取 XML 内容
        
        Args:
            source_file_path: DOCX 文件路径
            xml_name: XML 文件名（'document' 或 'footnotes'）
        
        Returns:
            str | None - XML 内容字符串，文件不存在返回 None
        """
        xml_path = f"word/{xml_name}.xml"
        with zipfile.ZipFile(source_file_path) as zipf:
            if xml_path not in zipf.namelist():
                return None
            return zipf.read(xml_path).decode("utf-8")

    def _read_and_simplify_xml(self, source_file_path: Path, xml_name: str, 
                              force_baseline: bool = False) -> str | None:
        """读取并简化 XML，返回简化后内容或 None（文件不存在）"""
        content = self._read_xml_from_docx(source_file_path, xml_name)
        if content is None:
            return None
        
        # 预处理 XML 内容（简化 + 格式标准化）
        simplified_content = self._preprocess_xml_content(content, source_file_path, force_baseline=force_baseline)
        
        # 若简化后有变化，备份并写回源文件
        if simplified_content != content:
            xml_path = f"word/{xml_name}.xml"
            self._print_simplify_stats(f"{xml_name}.xml", content, simplified_content)
            if self.simplify_options.get("enable_diff_log", True):
                try:
                    self._write_diff_log(source_file_path, content, simplified_content)
                except Exception:
                    pass
            
            # 备份原文件
            if self.simplify_options.get("backup_before_simplify", True):
                self._backup_file(source_file_path)
            
            self._save_simplified_content(source_file_path, {xml_path: simplified_content})
        
        return simplified_content

    def read_xml_soup(self, source_file_path: Path, xml_name: str = 'document', 
                     force_baseline: bool = False) -> BeautifulSoup | None:
        """读取 XML 并返回 BeautifulSoup 对象（用于 individual run 模式）。

        Args:
            source_file_path: DOCX 文件路径
            xml_name: 要读取的 XML 文件名（'document' 或 'footnotes'）
            force_baseline: 是否强制使用基线简化

        Returns:
            BeautifulSoup | None - XML DOM 对象（文件不存在返回 None）
        """
        simplified_content = self._read_and_simplify_xml(source_file_path, xml_name, force_baseline)
        if simplified_content is None:
            return None
        
        return BeautifulSoup(simplified_content, 'xml')

    def read_paragraphs(self, source_file_path: Path, xml_name: str = 'document', 
                       with_mapping: bool = False, skip_simplify: bool = False) -> list[str] | tuple[list[str], list[dict], BeautifulSoup] | None:
        """读取段落文本列表（用于 merged paragraph 模式）。

        Args:
            source_file_path: DOCX 文件路径
            xml_name: 要读取的 XML 文件名（'document' 或 'footnotes'）
            with_mapping: 是否返回 run 映射（Writer 需要）
            skip_simplify: 是否跳过简化（Writer 读取时使用，Reader 已简化过）

        Returns:
            - with_mapping=False: List[str] | None - 段落文本列表
            - with_mapping=True: (paragraph_list, run_mapping, xml_soup) | None
        """
        # 根据 skip_simplify 决定是否简化
        if skip_simplify:
            content = self._read_xml_from_docx(source_file_path, xml_name)
            if content is None:
                return None
            xml_soup = BeautifulSoup(content, 'xml')
        else:
            simplified_content = self._read_and_simplify_xml(source_file_path, xml_name)
            if simplified_content is None:
                return None
            xml_soup = BeautifulSoup(simplified_content, 'xml')
        
        paragraphs = []
        run_mapping = [] if with_mapping else None
        
        for p in xml_soup.find_all('w:p', recursive=True):
            t_tags = p.find_all('w:t', recursive=True)
            if not t_tags:
                continue
            
            original_texts = [t.get_text() or '' for t in t_tags]
            
            # 生成带边界标记的文本（用于翻译）
            parts = []
            for i, text in enumerate(original_texts):
                if text:
                    # 先添加边界标记（除了第一个）
                    if parts:
                        parts.append(f'<RUNBND{i}>')
                    
                    # 然后添加文本，如果是红色斜体则用 <NOTRANS> 包裹
                    if self._is_italic_marked_run(t_tags[i]):
                        parts.append(f'<NOTRANS>{text}</NOTRANS>')
                    else:
                        parts.append(text)
            
            boundary_text = ''.join(parts)
            
            if boundary_text:
                paragraphs.append(boundary_text)
                
                if with_mapping:
                    run_mapping.append({
                        'tags': t_tags,
                        'original_texts': original_texts,
                        'boundary_marker': boundary_text
                    })
        
        # 智能合并不完整段落 - Reader 和 Writer 都需要执行以保持一致性
        if with_mapping:
            # 需要同时合并 paragraphs 和 run_mapping
            paragraphs, run_mapping = self._merge_incomplete_paragraphs_with_mapping(paragraphs, run_mapping)
        else:
            paragraphs = self._merge_incomplete_paragraphs(paragraphs)
        
        return (paragraphs, run_mapping, xml_soup) if with_mapping else paragraphs

    def _merge_incomplete_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """智能合并被错误分割的段落
        
        检测以下情况并合并:
        1. 段落以常见中文连接词结尾(但、而、且、或、因此等)
        2. 段落以不完整动词短语结尾(可以X、能够X、将要X等)
        3. 下一段落不以新起点标记开头(数字编号、标题等)
        
        Args:
            paragraphs: 原始段落列表
            
        Returns:
            合并后的段落列表
        """
        import re
        
        if len(paragraphs) <= 1:
            return paragraphs
        
        # 中文不完整结尾模式
        incomplete_patterns = [
            r'[可以能将是在有][治疗做进行得到能够]$',  # 不完整动词短语
            r'[，、；但而且或及以与和]$',  # 连接词
            r'[的地得]$',  # 结构助词
            r'[了着过]$',  # 动态助词(可疑)
        ]
        
        # 新段落开始标记(这些段落不应该被合并到前面)
        new_paragraph_patterns = [
            r'^\d+[\.、]',  # 数字编号开头
            r'^[一二三四五六七八九十]+[、．]',  # 中文数字编号
            r'^[(（]\d+[)）]',  # 括号数字
            r'^[A-Z][a-z]+\s',  # 英文标题开头
            r'^[第章节]',  # 章节标记
        ]
        
        merged = []
        i = 0
        
        while i < len(paragraphs):
            current = paragraphs[i]
            
            # 移除边界标记和NOTRANS标签后检查
            clean_text = re.sub(r'<RUNBND\d+>|<NOTRANS>|</NOTRANS>', '', current)
            
            # 检查当前段落是否不完整
            is_incomplete = False
            for pattern in incomplete_patterns:
                if re.search(pattern, clean_text):
                    is_incomplete = True
                    break
            
            # 如果不完整且有下一段落
            if is_incomplete and i + 1 < len(paragraphs):
                next_para = paragraphs[i + 1]
                next_clean = re.sub(r'<RUNBND\d+>|<NOTRANS>|</NOTRANS>', '', next_para)
                
                # 检查下一段落是否是新起点
                is_new_start = False
                for pattern in new_paragraph_patterns:
                    if re.match(pattern, next_clean):
                        is_new_start = True
                        break
                
                # 如果下一段落不是新起点,则合并
                if not is_new_start:
                    merged.append(current + next_para)
                    i += 2  # 跳过下一段落
                    continue
            
            # 否则保持原样
            merged.append(current)
            i += 1
        
        return merged

    def _merge_incomplete_paragraphs_with_mapping(self, paragraphs: list[str], run_mapping: list[dict]) -> tuple[list[str], list[dict]]:
        """智能合并被错误分割的段落(带 run_mapping 同步合并)
        
        与 _merge_incomplete_paragraphs 功能相同,但同时合并对应的 run_mapping
        
        Args:
            paragraphs: 原始段落列表
            run_mapping: 原始 run_mapping 列表
            
        Returns:
            (合并后的段落列表, 合并后的 run_mapping 列表)
        """
        import re
        
        if len(paragraphs) <= 1:
            return paragraphs, run_mapping
        
        # 中文不完整结尾模式
        incomplete_patterns = [
            r'[可以能将是在有][治疗做进行得到能够]$',  # 不完整动词短语
            r'[，、；但而且或及以与和]$',  # 连接词
            r'[的地得]$',  # 结构助词
            r'[了着过]$',  # 动态助词(可疑)
        ]
        
        # 新段落开始标记
        new_paragraph_patterns = [
            r'^\d+[\.、]',  # 数字编号开头
            r'^[一二三四五六七八九十]+[、．]',  # 中文数字编号
            r'^[(（]\d+[)）]',  # 括号数字
            r'^[A-Z][a-z]+\s',  # 英文标题开头
            r'^[第章节]',  # 章节标记
        ]
        
        merged_paragraphs = []
        merged_mapping = []
        i = 0
        
        while i < len(paragraphs):
            current = paragraphs[i]
            current_map = run_mapping[i]
            
            # 移除边界标记和NOTRANS标签后检查
            clean_text = re.sub(r'<RUNBND\d+>|<NOTRANS>|</NOTRANS>', '', current)
            
            # 检查当前段落是否不完整
            is_incomplete = False
            for pattern in incomplete_patterns:
                if re.search(pattern, clean_text):
                    is_incomplete = True
                    break
            
            # 如果不完整且有下一段落
            if is_incomplete and i + 1 < len(paragraphs):
                next_para = paragraphs[i + 1]
                next_map = run_mapping[i + 1]
                next_clean = re.sub(r'<RUNBND\d+>|<NOTRANS>|</NOTRANS>', '', next_para)
                
                # 检查下一段落是否是新起点
                is_new_start = False
                for pattern in new_paragraph_patterns:
                    if re.match(pattern, next_clean):
                        is_new_start = True
                        break
                
                # 如果下一段落不是新起点,则合并
                if not is_new_start:
                    # 合并段落文本
                    merged_paragraphs.append(current + next_para)
                    
                    # 合并 run_mapping: 将两个段落的 tags 和 texts 合并
                    merged_mapping.append({
                        'tags': current_map['tags'] + next_map['tags'],
                        'original_texts': current_map['original_texts'] + next_map['original_texts'],
                        'boundary_marker': current + next_para
                    })
                    
                    i += 2  # 跳过下一段落
                    continue
            
            # 否则保持原样
            merged_paragraphs.append(current)
            merged_mapping.append(current_map)
            i += 1
        
        return merged_paragraphs, merged_mapping

    def _clean_extra_spaces(self, text: str) -> str:
        """清理文本中的多余空格"""
        import re
        text = re.sub(r' {2,}', ' ', text).strip()  # 合并连续空格并去除首尾
        # 清理中文标点前后空格
        text = re.sub(r' +([，。！？、；：）】」』])', r'\1', text)
        text = re.sub(r'([，。！？、；：（【「『]) +', r'\1', text)
        return text
    
    def _set_tag_text(self, tag: Tag, text: str, preserve_space: bool = False) -> None:
        """安全地设置 w:t 标签的文本，保留必要的属性，并为拉丁/西里尔文本设置语言避免单词断行。
        
        Word 如果把段落语言视为中文，会在任何字符间断行。对包含西文或俄文的 run 自动设置 w:lang，防止在单词内部断行。

        Args:
            tag: w:t 标签
            text: 要设置的文本
            preserve_space: 是否强制保留 xml:space="preserve" 属性
        """
        # 保存原有的 xml:space 属性
        original_space = tag.get('xml:space')
        
        # 设置文本
        tag.string = text
        
        # 恢复或设置 xml:space 属性
        if preserve_space or original_space == 'preserve':
            tag['xml:space'] = 'preserve'
        elif text and (text.startswith(' ') or text.endswith(' ')):
            tag['xml:space'] = 'preserve'
        elif 'xml:space' in tag.attrs and original_space != 'preserve':
            del tag['xml:space']

        # 如果包含西文或俄文字符，设置语言以避免单词中断行
        lang = self._detect_run_lang(text)
        if lang:
            self._ensure_run_lang(tag, lang)

    def _detect_run_lang(self, text: str) -> str | None:
        """检测文本语言：俄文优先，其次英文"""
        if not text:
            return None
        import re
        if re.search(r'[А-Яа-яЁё]', text):
            return 'ru-RU'
        if re.search(r'[A-Za-z]', text):
            return 'en-US'
        return None

    def _ensure_run_lang(self, t_tag: Tag, lang_val: str) -> None:
        """设置 run 的语言和字体，防止单词中间断行"""
        run = t_tag.find_parent('w:r')
        if not run:
            return
        
        # 获取或创建 rPr 和 new_tag 函数
        rpr = run.find('w:rPr')
        soup = getattr(t_tag, 'soup', None)
        new_tag_fn = None
        if rpr and hasattr(rpr, 'new_tag'):
            new_tag_fn = rpr.new_tag
        elif soup and hasattr(soup, 'new_tag'):
            new_tag_fn = soup.new_tag
        if not new_tag_fn:
            return
            
        if not rpr:
            rpr = new_tag_fn('w:rPr')
            run.insert(0, rpr)
        
        # 设置语言
        lang = rpr.find('w:lang') or rpr.append(new_tag_fn('w:lang')) or rpr.find('w:lang')
        lang['w:val'] = lang['w:eastAsia'] = lang_val

        # 为西文/俄文设置拉丁字体
        if lang_val in ('en-US', 'ru-RU'):
            rfonts = rpr.find('w:rFonts')
            if not rfonts:
                rfonts = new_tag_fn('w:rFonts')
                rpr.insert(0, rfonts)
            
            # 批量设置字体（仅在未设置时）
            font = 'Times New Roman'
            for attr in ('w:ascii', 'w:hAnsi', 'w:cs'):
                if not rfonts.get(attr):
                    rfonts[attr] = font
    
    def write_paragraphs(self, run_mapping: list, translated_paragraphs: list) -> None:
        """将翻译后的段落文本写回到 XML DOM 中。
        
        注意：此方法通过修改 run_mapping 中的 tags 来间接修改原始 xml_soup。
        run_mapping 中的 tags 是 BeautifulSoup Tag 对象的引用，修改它们会自动
        反映到调用 read_paragraphs() 时返回的 xml_soup 中。
        
        智能分配策略（按优先级）：
        1. 边界标记分割 - 如果译文保留了 <RUNBND> 标记，精确映射到每个 run
        2. 保持空 run - 如果标记丢失，保持原本为空的 run 为空，其他 run 按比例分配
        3. 比例分配 - 按原文长度比例分配译文到各个 run

        Args:
            run_mapping: List[Dict] - 段落的 run 映射信息
                - 'tags': List[Tag] - BeautifulSoup Tag 对象的引用
                - 'original_texts': List[str] - 原始文本
                - 'boundary_marker': str - 带标记的文本
            translated_paragraphs: List[str] - 翻译后的段落列表（与 run_mapping 一一对应）
        """
        if len(run_mapping) != len(translated_paragraphs):
            raise ValueError(f"run_mapping 长度 ({len(run_mapping)}) 与 translated_paragraphs 长度 ({len(translated_paragraphs)}) 不匹配")

        for para_info, translated_text in zip(run_mapping, translated_paragraphs):
            tags = para_info['tags']
            original_texts = para_info['original_texts']
            
            if not tags:
                continue

            import re
            
            # 预处理：移除 <NOTRANS> 标记（保留内容）
            # 这些标记已经完成使命（告诉翻译模型不翻译），写入时直接移除
            translated_text = re.sub(r'<NOTRANS>(.*?)</NOTRANS>', r'\1', translated_text)
            
            # 策略1：尝试按边界标记分割（最精确）
            boundary_pattern = r'<RUNBND\d+>'
            markers_in_translation = re.findall(boundary_pattern, translated_text)
            
            # 计算原文中有多少个非空 run（应该有 len(非空run)-1 个标记）
            non_empty_original_count = sum(1 for txt in original_texts if txt)
            expected_markers = non_empty_original_count - 1
            
            if len(markers_in_translation) == expected_markers and expected_markers > 0:
                # 标记完整保留，使用精确分割（类似原始一对一替换）
                parts = re.split(boundary_pattern, translated_text)
                non_empty_idx = 0
                
                for i, (tag, orig_text) in enumerate(zip(tags, original_texts)):
                    if orig_text:  # 原本有文本的 run
                        if non_empty_idx < len(parts):
                            self._set_tag_text(tag, parts[non_empty_idx])
                            non_empty_idx += 1
                        else:
                            self._set_tag_text(tag, '')
                    else:
                        # 原本为空的 run，保持为空（保留 xml:space 属性）
                        self._set_tag_text(tag, '', preserve_space=True)
                continue
            
            # 策略2：标记丢失，移除边界标记
            cleaned_text = re.sub(boundary_pattern, '', translated_text)
            
            # 清理多余空格
            cleaned_text = self._clean_extra_spaces(cleaned_text)
            
            # 找出原文中有内容的 run
            non_empty_indices = [i for i, txt in enumerate(original_texts) if txt]
            
            # 处理空run或单run情况
            if not non_empty_indices or len(non_empty_indices) == 1:
                target_idx = non_empty_indices[0] if non_empty_indices else -1
                for i, tag in enumerate(tags):
                    if i == target_idx:
                        self._set_tag_text(tag, cleaned_text)
                    else:
                        self._set_tag_text(tag, '', preserve_space=True)
                continue
            
            # 策略3：多个非空 run，按原文长度比例分配
            # 计算非空 run 的长度比例
            non_empty_lengths = [len(original_texts[i]) for i in non_empty_indices]
            total_length = sum(non_empty_lengths)
            
            if total_length == 0:
                # 理论上不应该发生（非空 run 的长度和为0）
                self._set_tag_text(tags[non_empty_indices[0]], cleaned_text)
                for i, tag in enumerate(tags):
                    if i != non_empty_indices[0]:
                        self._set_tag_text(tag, '', preserve_space=True)
                continue
            
            # 按比例分配译文到非空 run
            translated_length = len(cleaned_text)
            start_pos = 0
            
            for run_idx, (idx, orig_len) in enumerate(zip(non_empty_indices, non_empty_lengths)):
                if run_idx == len(non_empty_indices) - 1:
                    # 最后一个非空 run，分配剩余所有文本
                    self._set_tag_text(tags[idx], cleaned_text[start_pos:])
                else:
                    # 按比例计算分配长度
                    ratio = orig_len / total_length
                    allocated_length = int(translated_length * ratio)
                    
                    # 尝试智能断句
                    end_pos = start_pos + allocated_length
                    if end_pos < translated_length and allocated_length > 3:
                        search_window = min(20, allocated_length // 2)
                        search_end = min(translated_length, end_pos + search_window)
                        
                        for break_char in [' ', ',', '.', '，', '。', ';', '；']:
                            idx_found = cleaned_text.find(break_char, end_pos, search_end)
                            if idx_found != -1:
                                end_pos = idx_found + 1
                                break
                    
                    self._set_tag_text(tags[idx], cleaned_text[start_pos:end_pos])
                    start_pos = end_pos
            
            # 将所有原本为空的 run 设为空（保留 xml:space）
            for i, tag in enumerate(tags):
                if i not in non_empty_indices:
                    self._set_tag_text(tag, '', preserve_space=True)
                    
    def _backup_file(self, file_path: Path):
        """备份文件到同目录下，在文件名中添加 .backup 标记
        
        备份策略：
        - 如果已存在备份文件，不重复备份（保留首次备份）
        - 备份文件命名格式：原文件名.backup.docx
        - 示例：document.docx -> document.backup.docx
        """
        try:
            # 构建备份文件名：在扩展名前插入 .backup
            backup_path = file_path.with_stem(file_path.stem + '.backup')
            
            # 如果备份已存在，不重复备份
            if backup_path.exists():
                return
            
            # 复制文件到备份路径
            shutil.copy2(str(file_path), str(backup_path))
        except Exception:
            # 备份失败不影响主流程
            pass

    def _save_simplified_content(self, file_path: Path, data: dict):
        """保存简化后的内容到源文件"""
        # 使用临时文件避免同时读写同一文件导致损坏
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        try:
            # 先写入临时文件
            ZipUtil.replace_in_zip_file(file_path, tmp_path, data)
            # 然后用临时文件覆盖原文件
            shutil.move(str(tmp_path), str(file_path))
        except Exception as e:
            # 如果出错，删除临时文件
            if tmp_path.exists():
                tmp_path.unlink()
            raise e
    
    def _print_simplify_stats(self, file_name: str, original: str, simplified: str):
        """输出简化统计信息"""
        original_size = len(original)
        simplified_size = len(simplified)
        reduction = original_size - simplified_size
        reduction_percent = (reduction / original_size * 100) if original_size > 0 else 0
        
        original_runs = len(re.findall(r'<w:r>', original))
        simplified_runs = len(re.findall(r'<w:r>', simplified))
        
        print("\n" + "=" * 70)
        print(f"【{file_name} 简化统计】")
        print("=" * 70)
        print(f"大小对比:")
        print(f"  原始:     {original_size / 1024:>10.1f} KB ({original_size:>12,} 字节)")
        print(f"  简化后:   {simplified_size / 1024:>10.1f} KB ({simplified_size:>12,} 字节)")
        print(f"  节省:     {reduction / 1024:>10.1f} KB ({reduction_percent:>6.1f}%)")
        print(f"\n文本块对比:")
        print(f"  原始 run 数:   {original_runs:>8,}")
        print(f"  简化后 run 数: {simplified_runs:>8,}")
        print(f"  减少:         {original_runs - simplified_runs:>8,} ({((original_runs - simplified_runs) / original_runs * 100):.1f}%)")
        print("=" * 70 + "\n")

    def _write_diff_log(self, file_path: Path, original: str, simplified: str):
        """将简化前后的差异信息写入日志文件（简单摘要）"""
        if not self.simplify_options.get("enable_diff_log", True):
            return
        try:
            p = Path(file_path)
            log_name = p.with_suffix(p.suffix + f'.simplify.log')
            ts = datetime.now().isoformat()
            original_size = len(original)
            simplified_size = len(simplified)
            reduction = original_size - simplified_size
            original_runs = len(re.findall(r'<w:r>', original))
            simplified_runs = len(re.findall(r'<w:r>', simplified))
            with open(log_name, 'a', encoding='utf-8') as f:
                f.write(f'[{ts}] Simplify {p.name}\n')
                f.write(f'  Original bytes: {original_size}, Simplified bytes: {simplified_size}, Reduced: {reduction}\n')
                f.write(f'  Runs: original={original_runs}, simplified={simplified_runs}\n')
                f.write('\n')
        except Exception:
            # 不让日志影响主流程
            pass
