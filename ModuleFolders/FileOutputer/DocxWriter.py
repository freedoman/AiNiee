from pathlib import Path

from ModuleFolders.Cache.CacheFile import CacheFile
from ModuleFolders.Cache.CacheProject import ProjectType
from ModuleFolders.FileAccessor.DocxAccessor import DocxAccessor
from ModuleFolders.FileOutputer.BaseWriter import (
    BaseTranslatedWriter,
    OutputConfig,
    PreWriteMetadata
)
from ModuleFolders.BoundaryMarkerAlternative.format_extractor import FormatApplier
from ModuleFolders.BoundaryMarkerAlternative.position_mapper import PositionMapper, FormatMapping


class DocxWriter(BaseTranslatedWriter):
    def __init__(self, output_config: OutputConfig):
        super().__init__(output_config)
        self.file_accessor = DocxAccessor()
        self.format_applier = FormatApplier()
        # 使用 ratio 方法: 快速且对position属性有优化
        self.position_mapper = PositionMapper(default_method="ratio")
        # 从output_config读取配置，如果没有则使用默认值
        self.merge_mode = getattr(output_config, 'merge_mode', False)
        self.use_position_mapping = getattr(output_config, 'use_position_mapping', False)
        
        # 调试输出
        print(f"\n[DocxWriter.__init__]")
        print(f"  output_config.merge_mode = {getattr(output_config, 'merge_mode', 'NOT_SET')}")
        print(f"  output_config.use_position_mapping = {getattr(output_config, 'use_position_mapping', 'NOT_SET')}")
        print(f"  self.merge_mode = {self.merge_mode}")
        print(f"  self.use_position_mapping = {self.use_position_mapping}")

    def on_write_translated(
        self, translation_file_path: Path, cache_file: CacheFile,
        pre_write_metadata: PreWriteMetadata,
        source_file_path: Path = None,
    ):
        """
        固定接口：根据 OutputConfig 中的 merge_mode 动态选择行为
        - merge_mode=False：逐run写入（原有逻辑）
        - merge_mode=True：按段落合并写入（需与 Reader 的 merge_mode=True 配套使用）
        """
        print(f"\n[DocxWriter] merge_mode = {self.merge_mode}")
        print(f"[DocxWriter] use_position_mapping = {self.use_position_mapping}")
        print(f"[DocxWriter] cache文件项数 = {len(cache_file.items)}")
        
        if self.merge_mode:
            # 合并段落模式
            self._write_merged_paragraphs(translation_file_path, cache_file, source_file_path)
        else:
            # 默认逐run模式（原有逻辑）
            self._write_individual_runs(translation_file_path, cache_file, source_file_path)

    def _write_individual_runs(
        self, translation_file_path: Path, cache_file: CacheFile, source_file_path: Path = None
    ):
        """逐个 run 写入（修改所有 w:t 标签）
        
        注意：Reader和Writer都从简化后的XML读取
        - Reader第一次读取时会预处理简化XML并写回源文件
        - cache存储的是简化后的文本
        - Writer读取同样的简化后XML，应该能完美匹配
        """
        files_to_replace = {}
        
        # 处理正文和脚注
        for xml_name in ['document', 'footnotes']:
            xml_soup = self.file_accessor.read_xml_soup(source_file_path, xml_name)
            if xml_soup is None:
                continue
                
            is_footnote = (xml_name == 'footnotes')
            
            # 筛选对应的翻译项
            items = [
                item for item in cache_file.items 
                if bool(item.extra.get('footnote')) == is_footnote
            ]
            
            # 调试统计
            total_t_tags = 0
            matched_count = 0
            unmatched_samples = []
            
            # 遍历所有 w:t 标签并替换（顺序匹配）
            start_index = 0
            for match in xml_soup.find_all("w:t"):
                if isinstance(match.string, str) and match.string.strip():
                    total_t_tags += 1
                    matched = False
                    
                    # 从当前位置向后查找匹配的cache项
                    for content_index in range(start_index, len(items)):
                        if match.string == items[content_index].source_text:
                            match.string = items[content_index].final_text
                            start_index = content_index + 1
                            matched = True
                            matched_count += 1
                            break
                    
                    # 记录未匹配的样本（最多5个）
                    if not matched and len(unmatched_samples) < 5:
                        unmatched_samples.append({
                            'xml_text': match.string[:50],
                            'xml_len': len(match.string),
                            'cache_idx': start_index,
                            'next_cache': items[start_index].source_text[:50] if start_index < len(items) else 'N/A'
                        })
            
            # 打印调试信息
            if total_t_tags > 0:
                print(f"\n[merge_mode=False 写入调试] {xml_name}.xml")
                print(f"  XML中w:t标签数: {total_t_tags}")
                print(f"  Cache项数: {len(items)}")
                print(f"  匹配成功: {matched_count}/{total_t_tags} ({matched_count*100/total_t_tags:.1f}%)")
                
                if unmatched_samples:
                    print(f"  ❌ 未匹配样本 (从cache索引{unmatched_samples[0]['cache_idx']}开始):")
                    for i, sample in enumerate(unmatched_samples, 1):
                        print(f"    {i}. XML文本(长{sample['xml_len']}): '{sample['xml_text']}'")
                        print(f"       期望Cache: '{sample['next_cache']}'")
                    print(f"\n  可能原因:")
                    print(f"    1. Reader/Writer读取的XML版本不一致")
                    print(f"    2. 预处理简化的时机问题")
                    print(f"    3. Cache文件是旧的，需要删除重新翻译")
            
            files_to_replace[f"word/{xml_name}.xml"] = str(xml_soup)
        
        self._write_files_to_docx(source_file_path, translation_file_path, files_to_replace)

    def _write_merged_paragraphs(
        self, translation_file_path: Path, cache_file: CacheFile, source_file_path: Path = None
    ):
        """按合并段落写入翻译结果，支持正文、脚注和位置映射格式"""
        files_to_replace = {}
        
        print(f"\n[_write_merged_paragraphs] 开始写入")
        print(f"  源文件: {source_file_path.name if source_file_path else 'N/A'}")
        print(f"  目标文件: {translation_file_path.name}")
        print(f"  use_position_mapping: {self.use_position_mapping}")
        print(f"  cache总项数: {len(cache_file.items)}")
        
        # 统计翻译状态
        untranslated_count = sum(1 for item in cache_file.items 
                                if item.final_text == item.source_text)
        print(f"  未翻译段落数(final_text==source_text): {untranslated_count}/{len(cache_file.items)}")
        
        # 检查前几个cache items的extra信息
        if cache_file.items:
            print(f"\n  前3个cache items的extra信息:")
            for i, item in enumerate(cache_file.items[:3], 1):
                extra_keys = list(item.extra.keys()) if item.extra else []
                has_merged = item.extra.get('merged', False) if item.extra else False
                has_footnote = item.extra.get('footnote', 0) if item.extra else 0
                print(f"    Item {i}: keys={extra_keys}, merged={has_merged}, footnote={has_footnote}")
        
        # 处理正文和脚注
        for xml_name in ['document', 'footnotes']:
            is_footnote = (xml_name == 'footnotes')
            
            # 筛选对应的翻译项
            items = [
                item for item in cache_file.items
                if item.extra.get('merged') and 
                   bool(item.extra.get('footnote')) == is_footnote
            ]
            
            print(f"\n  处理 {xml_name}.xml: {len(items)} 个段落")
            
            if not items:
                continue
            
            # 检查第一个item是否有run_formats
            has_formats = items[0].extra.get('run_formats') is not None
            print(f"    第一个item有run_formats: {has_formats}")
            
            # 检查是否使用位置映射
            if self.use_position_mapping and items[0].extra.get('run_formats'):
                # 位置映射模式：应用映射后的格式
                xml_soup = self.file_accessor.read_xml_soup(source_file_path, xml_name)
                if xml_soup:
                    paragraphs = xml_soup.find_all('w:p')
                    
                    for item in items:
                        # 使用 xml_index 定位 XML 中的实际段落位置
                        xml_index = item.extra.get('xml_index', item.extra.get('para_index', 0))
                        if xml_index >= len(paragraphs):
                            continue
                        
                        para = paragraphs[xml_index]
                        source_formats = item.extra.get('run_formats', [])
                        
                        if source_formats:
                            # 将字典格式转换为 RunFormat 对象
                            from ModuleFolders.BoundaryMarkerAlternative.position_mapper import RunFormat
                            source_runs = []
                            for fmt in source_formats:
                                if isinstance(fmt, dict):
                                    run = RunFormat(
                                        start=fmt.get('start', 0),
                                        end=fmt.get('end', 0),
                                        bold=fmt.get('bold', False),
                                        italic=fmt.get('italic', False),
                                        underline=fmt.get('underline', False),
                                        color=fmt.get('color'),
                                        font_name=fmt.get('font_name'),
                                        font_size=fmt.get('font_size'),
                                        vert_align=fmt.get('vert_align'),
                                        position=fmt.get('position')
                                    )
                                    source_runs.append(run)
                                else:
                                    source_runs.append(fmt)  # 已经是 RunFormat 对象
                            
                            # 创建格式映射
                            import re
                            source_clean = re.sub(r'<RUNBND\d+>', '', item.source_text)
                            target_clean = re.sub(r'<RUNBND\d+>', '', item.final_text)
                            
                            mapping = FormatMapping(
                                source_text=source_clean,
                                target_text=target_clean,
                                source_runs=source_runs
                            )
                            
                            # 执行格式映射
                            result = self.position_mapper.map_format(mapping)
                            
                            # 调试输出
                            print(f"\n[位置映射] 段落 {xml_index}")
                            print(f"  原文: {source_clean[:100]}...")
                            print(f"  译文: {target_clean[:100]}...")
                            print(f"  原文==译文? {source_clean == target_clean}")
                            print(f"  译文长度: {len(target_clean)}")
                            print(f"  映射方法: {result.mapping_method}")
                            print(f"  原文格式数: {len(result.source_runs)}")
                            print(f"  译文格式数: {len(result.target_runs)}")
                            
                            # 检查源格式中的特殊格式
                            source_special = []
                            for run in result.source_runs:
                                if run.vert_align:
                                    source_special.append(f"vertAlign={run.vert_align}")
                                if run.position is not None:
                                    source_special.append(f"position={run.position}")
                            if source_special:
                                print(f"  源格式特殊属性: {', '.join(source_special[:5])}")
                            
                            # 检查格式覆盖范围
                            if result.target_runs:
                                covered_chars = set()
                                for run in result.target_runs:
                                    for i in range(run.start, run.end):
                                        covered_chars.add(i)
                                coverage = len(covered_chars) / len(target_clean) if len(target_clean) > 0 else 0
                                print(f"  格式覆盖率: {coverage*100:.1f}% ({len(covered_chars)}/{len(target_clean)})")
                                
                                # 显示前几个格式的范围
                                for i, run in enumerate(result.target_runs[:3]):
                                    text_segment = target_clean[run.start:run.end]
                                    format_info = []
                                    if run.bold: format_info.append("bold")
                                    if run.italic: format_info.append("italic")
                                    if run.vert_align: format_info.append(f"vert={run.vert_align}")
                                    if run.position is not None: format_info.append(f"pos={run.position}")
                                    fmt_str = f" ({', '.join(format_info)})" if format_info else ""
                                    print(f"    格式{i+1}: [{run.start}:{run.end}]{fmt_str} '{text_segment}'")
                            
                            # 直接在原段落上修改,不使用 FormatApplier
                            # 删除原段落的所有文本runs
                            for old_run in para.find_all('w:r'):
                                old_run.decompose()
                            
                            # 根据映射后的格式创建新的runs
                            for run_format in result.target_runs:
                                # 提取该run的文本
                                run_text = result.target_text[run_format.start:run_format.end]
                                
                                # 创建新的run元素
                                new_run = xml_soup.new_tag('w:r')
                                
                                # 添加格式属性(如果有)
                                if any([run_format.bold, run_format.italic, run_format.underline, 
                                       run_format.color, run_format.font_name, run_format.font_size, 
                                       run_format.vert_align, run_format.position]):
                                    rpr = xml_soup.new_tag('w:rPr')
                                    
                                    if run_format.bold:
                                        rpr.append(xml_soup.new_tag('w:b'))
                                    if run_format.italic:
                                        rpr.append(xml_soup.new_tag('w:i'))
                                    if run_format.underline:
                                        u_tag = xml_soup.new_tag('w:u')
                                        u_tag['w:val'] = 'single'
                                        rpr.append(u_tag)
                                    if run_format.color:
                                        color_tag = xml_soup.new_tag('w:color')
                                        color_tag['w:val'] = run_format.color
                                        rpr.append(color_tag)
                                    if run_format.font_name:
                                        font_tag = xml_soup.new_tag('w:rFonts')
                                        font_tag['w:ascii'] = run_format.font_name
                                        font_tag['w:hAnsi'] = run_format.font_name
                                        rpr.append(font_tag)
                                    if run_format.font_size:
                                        sz_tag = xml_soup.new_tag('w:sz')
                                        sz_tag['w:val'] = str(run_format.font_size * 2)
                                        rpr.append(sz_tag)
                                    if run_format.vert_align:
                                        vert_tag = xml_soup.new_tag('w:vertAlign')
                                        vert_tag['w:val'] = run_format.vert_align
                                        rpr.append(vert_tag)
                                    if run_format.position is not None:
                                        pos_tag = xml_soup.new_tag('w:position')
                                        pos_tag['w:val'] = str(run_format.position)
                                        rpr.append(pos_tag)
                                    
                                    new_run.append(rpr)
                                
                                # 添加文本内容
                                t_tag = xml_soup.new_tag('w:t')
                                t_tag['xml:space'] = 'preserve'
                                t_tag.string = run_text
                                new_run.append(t_tag)
                                
                                # 将run添加到段落
                                para.append(new_run)
                            
                            # 验证结果
                            new_text = ''.join([t.string for t in para.find_all('w:t') if t.string])
                            print(f"  新段落文本: {new_text[:100]}...")
                            print(f"  新文本==原文? {new_text == source_clean}")
                            print(f"  新文本==译文? {new_text == target_clean}")
                            print(f"  ✓ 段落内容已更新")
                    
                    files_to_replace[f"word/{xml_name}.xml"] = str(xml_soup)
            else:
                # 传统模式：使用边界标记
                result = self.file_accessor.read_paragraphs(
                    source_file_path, xml_name=xml_name, 
                    with_mapping=True, skip_simplify=True
                )
                if result is None:
                    continue
                    
                _, run_mapping, xml_soup = result
                
                # 提取翻译文本
                translated_paragraphs = [item.final_text for item in items]
                
                # 长度匹配检查：只使用有效的 run_mapping 项
                # 过滤掉空段落对应的 run_mapping
                if len(run_mapping) != len(translated_paragraphs):
                    # 根据非空段落数量调整 run_mapping
                    valid_run_mapping = []
                    para_idx = 0
                    for mapping in run_mapping:
                        # 检查该 mapping 对应的原始段落是否为空
                        if mapping and para_idx < len(translated_paragraphs):
                            valid_run_mapping.append(mapping)
                            para_idx += 1
                    run_mapping = valid_run_mapping[:len(translated_paragraphs)]
                
                # 将译文写回到 XML DOM
                self.file_accessor.write_paragraphs(run_mapping, translated_paragraphs)
                files_to_replace[f"word/{xml_name}.xml"] = str(xml_soup)
        
        self._write_files_to_docx(source_file_path, translation_file_path, files_to_replace)

    def _write_files_to_docx(self, source_path: Path, target_path: Path, files: dict):
        """将文件写入 DOCX（统一写入逻辑）"""
        from ModuleFolders.FileAccessor import ZipUtil
        ZipUtil.replace_in_zip_file(source_path, target_path, files)

    @classmethod
    def get_project_type(self):
        return ProjectType.DOCX
