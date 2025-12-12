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
            "strip_spacing": "zeros",  # 'none' | 'zeros' | 'small'
            "enable_diff_log": True,
            "protect_vertalign": True,  # 保护上标/下标 run 不被合并
            "simplify_mode": "balanced",  # conservative | balanced | aggressive
            "merge_mode": True,  # 启用合并段落模式
            **(simplify_options or {})
        }

    def _simplify_xml_content(self, content: str, source_file_path: Path | None = None, force_baseline: bool = False) -> str:
        """简化 XML 内容，移除冗余标签"""
        if force_baseline:
            return self._apply_baseline_simplify(content)
        
        mode = self.simplify_options.get("simplify_mode", "balanced")
        
        # 步骤1: 基础清理（所有模式）
        content = self._remove_redundant_colors(content)
        content = self._deduplicate_font_sizes(content)
        content = self._remove_empty_format_blocks(content)
        
        # 步骤2: 清理零值间距（仅 aggressive 模式）
        if mode == "aggressive":
            content = self._remove_zero_spacing(content)
        
        # 步骤3: 合并相同格式的 runs（conservative 模式跳过）
        if mode != "conservative":
            content = self._merge_format_runs(content)
        
        # 步骤4: 合并连续空格（所有模式安全）
        content = self._merge_consecutive_spaces(content)
        
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
    
    def _remove_zero_spacing(self, content: str) -> str:
        """移除零值 spacing（aggressive 模式，需谨慎）"""
        strip_spacing = self.simplify_options.get("strip_spacing", "zeros")
        if strip_spacing != "zeros":
            return content
        
        try:
            soup = BeautifulSoup(content, "xml")
            for spacing in soup.find_all('w:spacing'):
                val = spacing.get('w:val') or spacing.get('val')
                parent_name = spacing.parent.name if spacing.parent else None
                if val == '0' and parent_name == 'w:rPr':
                    spacing.decompose()
            return str(soup)
        except Exception:
            return re.sub(r'<w:spacing w:val="0"\s*/>', '', content)
    
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

    def _merge_adjacent_format_runs(self, content: str) -> str:
        """合并相邻的相同格式 run（保护上标/下标）"""
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
                return f'<w:r><w:rPr>{m.group(2)}</w:rPr><w:t>{m.group(3)}{m.group(6)}</w:t></w:r>'
            return m.group(0)
        
        return re.sub(pattern, replacer, content, flags=re.DOTALL)

    def read_content(self, source_file_path: Path, force_baseline: bool = False):
        with zipfile.ZipFile(source_file_path) as zipf:
            content = zipf.read("word/document.xml").decode("utf-8")
        
        # 先对 XML 进行简化（传入源路径以便日志，force_baseline 用于诊断）
        simplified_content = self._simplify_xml_content(content, source_file_path, force_baseline=force_baseline)

        # 如果简化后有变化，立即保存到源文件
        if simplified_content != content:
            self._print_simplify_stats("document.xml", content, simplified_content)
            if self.simplify_options.get("enable_diff_log", True):
                try:
                    self._write_diff_log(source_file_path, content, simplified_content)
                except Exception:
                    pass
            self._save_simplified_content(source_file_path, {"word/document.xml": simplified_content})
        
        # 读取xml内容
        xml_soup = BeautifulSoup(simplified_content, 'xml')

        # 遍历每个段落并合并相邻且格式相同的 run
        for paragraph in xml_soup.find_all('w:p', recursive=True):
            self._merge_adjacent_same_style_run(paragraph)
        return xml_soup
    
    def read_footnotes(self, source_file_path: Path, force_baseline: bool = False):
        with zipfile.ZipFile(source_file_path) as zipf:
            for item in zipf.infolist():
                # 查找是否有脚注文件
                if item.filename == "word/footnotes.xml":
                    footnotes = zipf.read("word/footnotes.xml").decode("utf-8")
                    
                    # 先对 XML 进行简化（传入源路径以便日志，force_baseline 用于诊断）
                    simplified_footnotes = self._simplify_xml_content(footnotes, source_file_path, force_baseline=force_baseline)
                    
                    # 如果简化后有变化，立即保存到源文件
                    if simplified_footnotes != footnotes:
                        self._print_simplify_stats("footnotes.xml", footnotes, simplified_footnotes)
                        if self.simplify_options.get("enable_diff_log", True):
                            try:
                                self._write_diff_log(source_file_path, footnotes, simplified_footnotes)
                            except Exception:
                                pass
                        self._save_simplified_content(source_file_path, {"word/footnotes.xml": simplified_footnotes})
                    
                    xml_soup = BeautifulSoup(simplified_footnotes, "xml")
                    for paragraph in xml_soup.find_all('w:p', recursive=True):
                        self._merge_adjacent_same_style_run(paragraph)
                    return xml_soup
            return None

    def read_merged_text(self, source_file_path: Path, force_baseline: bool = False, paragraph_separator: str = "\n", join_empty: bool = False) -> str:
        """读取并返回合并后的纯文本，便于批量翻译。

        行为：
        - 将每个段落 (`w:p`) 中的所有 run (`w:t`) 文本按出现顺序合并为一个段落文本。
        - 使用 `paragraph_separator` 作为段落之间的分隔（默认换行）。
        - `join_empty=True` 时也会保留空段落（作为分隔符），否则跳过空段落。

        返回：合并后的字符串（不会修改原始 docx）。
        """
        with zipfile.ZipFile(source_file_path) as zipf:
            content = zipf.read("word/document.xml").decode("utf-8")

        simplified_content = self._simplify_xml_content(content, source_file_path, force_baseline=force_baseline)

        # 使用 BeautifulSoup 解析并按段落合并 run 文本
        xml_soup = BeautifulSoup(simplified_content, 'xml')
        paragraphs = []

        for p in xml_soup.find_all('w:p', recursive=True):
            # 收集段落中所有的文本节点（w:t）并按顺序拼接
            texts = []
            for t in p.find_all('w:t', recursive=True):
                txt = t.get_text() or ''
                texts.append(txt)
            para_text = ''.join(texts)
            if para_text or join_empty:
                paragraphs.append(para_text)

        if not paragraphs:
            return ''

        return paragraph_separator.join(paragraphs)

    def read_and_get_runs(self, source_file_path: Path, force_baseline: bool = False) -> tuple:
        """读取合并文本并记录每个 run 的映射，便于翻译后写回。

        返回 (merged_text, run_mapping, xml_soup)，其中：
        - merged_text: 按段落合并的纯文本
        - run_mapping: List[Dict]，每个字典包含：
          * 'tags': List[Tag] - 该段落的所有 w:t 标签
          * 'original_texts': List[str] - 每个 run 的原始文本（用于精确匹配）
          * 'boundary_marker': str - 边界标记分隔的文本（用于翻译）
        - xml_soup: BeautifulSoup 解析后的 XML，用于后续写入
        """
        with zipfile.ZipFile(source_file_path) as zipf:
            content = zipf.read("word/document.xml").decode("utf-8")

        simplified_content = self._simplify_xml_content(content, source_file_path, force_baseline=force_baseline)
        xml_soup = BeautifulSoup(simplified_content, 'xml')

        paragraphs = []
        run_mapping = []  # 每个段落对应的结构化信息

        for p in xml_soup.find_all('w:p', recursive=True):
            t_tags = p.find_all('w:t', recursive=True)
            if not t_tags:
                continue
            
            # 收集每个 run 的原始文本
            original_texts = [t.get_text() or '' for t in t_tags]
            
            # 生成带边界标记的文本（只在非空 run 之间插入标记）
            parts = []
            for i, text in enumerate(original_texts):
                if text:  # 只添加非空文本
                    if parts:  # 如果不是第一个非空run，添加边界标记
                        parts.append(f'<RUNBND{i}>')
                    parts.append(text)
            
            para_text = ''.join(original_texts)
            if para_text:  # 只保留非空段落
                paragraphs.append(''.join(parts))  # 使用带标记的文本
                run_mapping.append({
                    'tags': t_tags,
                    'original_texts': original_texts,
                    'boundary_marker': ''.join(parts)
                })

        merged_text = '\n'.join(paragraphs)
        return merged_text, run_mapping, xml_soup

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
    
    def write_merged_text(self, xml_soup, run_mapping: list, translated_paragraphs: list) -> None:
        """根据翻译后的段落文本和 run 映射，替换 XML 中的文本内容。
        
        策略：
        1. 优先尝试按边界标记分割（精确匹配，类似原始一对一替换）
        2. 如果标记丢失，降级为保持空 run 为空 + 只替换有内容的 run
        3. 最差情况，按比例分配

        Args:
            xml_soup: BeautifulSoup 对象（来自 read_and_get_runs 返回值）
            run_mapping: List[Dict]，每个字典包含 tags、original_texts、boundary_marker
            translated_paragraphs: List[str]，翻译后的段落文本列表（与 run_mapping 长度相同）
        """
        if len(run_mapping) != len(translated_paragraphs):
            raise ValueError(f"run_mapping 长度 ({len(run_mapping)}) 与 translated_paragraphs 长度 ({len(translated_paragraphs)}) 不匹配")

        for para_info, translated_text in zip(run_mapping, translated_paragraphs):
            tags = para_info['tags']
            original_texts = para_info['original_texts']
            
            if not tags:
                continue

            # 策略1：尝试按边界标记分割（最精确）
            # 检查译文中是否保留了边界标记
            import re
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
            
            # 策略2：标记丢失，保持空 run 为空，只对有文本的 run 进行处理
            # 移除所有标记（如果有残留）
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
    
    def write_content(
        self, content: BeautifulSoup, footnotes: BeautifulSoup, write_file_path: Path,
        source_file_path: Path,
    ):
        # 准备要写入的文件数据
        data = {}
        if content:
            data["word/document.xml"] = str(content)
        if footnotes:
            data["word/footnotes.xml"] = str(footnotes)
        ZipUtil.replace_in_zip_file(
            source_file_path, write_file_path, data
        )


    def _get_style(self, run: Tag):
        rpr = run.find("w:rPr")
        if not rpr:
            return {}
        return {
            tag.name: tag.attrs for tag in rpr.find_all(recursive=False)
        }

    def _is_tag_of(self, ele: PageElement, tag_name: str):
        return isinstance(ele, Tag) and ele.name == tag_name

    def _is_empty_string(self, ele: PageElement):
        return isinstance(ele, NavigableString) and ele.strip() == ""

    def _merge_adjacent_same_style_run(self, paragraph: Tag):

        # 排除掉语法检测和空字符串
        child_nodes = [
            ele for ele in paragraph.children
            if not self._is_tag_of(ele, "proofErr") and not self._is_empty_string(ele)
        ]
        new_children = []
        i = 0
        n = len(child_nodes)

        while i < n:
            current = child_nodes[i]

            # 如果不是run节点，直接保留
            if not self._is_tag_of(current, "r"):
                new_children.append(current)
                i += 1
                continue
            # 如果是 run 节点，但是没有文本内容也直接保留
            elif not (current_text := current.find("w:t")) or current_text.string is None:
                new_children.append(current)
                i += 1
                continue

            # 如果是run节点，尝试合并后续相同格式的run
            merged_run = current
            j = i + 1
            while j < n:
                next_node = child_nodes[j]

                # 遇到其他类型节点，停止合并
                if not self._is_tag_of(current, "r"):
                    break

                # 格式相同则合并文本内容，并且合并 rPr（取并集以保留如 w:spacing 等属性）
                if self._get_style(merged_run) == self._get_style(next_node):
                    # 合并 rPr：如果 next_node 有 rPr 中的关键属性(如 w:spacing)，确保保留到 merged_run
                    cur_rpr = merged_run.find("w:rPr")
                    next_rpr = next_node.find("w:rPr")
                    if next_rpr:
                        if not cur_rpr:
                            # 直接把 next_rpr 复制到 merged_run
                            merged_run.insert(0, next_rpr)
                        else:
                            # 对每个子标签，如果 merged_run 中没有则复制过去；如果有则保留原有（以 merged_run 为主）
                            for child in list(next_rpr.find_all(recursive=False)):
                                # 通过标签名来判断唯一性（例如 w:spacing、w:sz 等）
                                tag_name = child.name
                                exists = False
                                for existing in cur_rpr.find_all(recursive=False):
                                    if existing.name == tag_name:
                                        exists = True
                                        break
                                if not exists:
                                    cur_rpr.append(child)

                    # 合并文本
                    current_t = merged_run.find("w:t")
                    next_t = next_node.find("w:t")
                    if next_t:
                        if next_t.get("xml:space") == "preserve":
                            current_t["xml:space"] = "preserve"
                        current_t.string = (current_t.string or "") + next_t.get_text()
                    j += 1
                else:
                    break
            new_children.append(merged_run)
            i = j  # 跳过已处理的节点

        # 用重构后的子节点列表替换原始内容
        paragraph.clear()
        for node in new_children:
            paragraph.append(node)
