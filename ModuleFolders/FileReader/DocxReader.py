from pathlib import Path

from ModuleFolders.Cache.CacheFile import CacheFile
from ModuleFolders.Cache.CacheItem import CacheItem
from ModuleFolders.Cache.CacheProject import ProjectType
from ModuleFolders.FileAccessor.DocxAccessor import DocxAccessor
from ModuleFolders.FileReader.BaseReader import (
    BaseSourceReader,
    InputConfig,
    PreReadMetadata
)
from ModuleFolders.BoundaryMarkerAlternative.format_extractor import FormatExtractor


class DocxReader(BaseSourceReader):
    def __init__(self, input_config: InputConfig):
        super().__init__(input_config)
        self.file_accessor = DocxAccessor()
        self.format_extractor = FormatExtractor()
        # 从input_config读取配置，如果没有则使用默认值
        self.merge_mode = getattr(input_config, 'merge_mode', False)
        self.extract_formats = getattr(input_config, 'extract_formats', False)
        
        # 调试输出
        print(f"\n[DocxReader.__init__]")
        print(f"  input_config.merge_mode = {getattr(input_config, 'merge_mode', 'NOT_SET')}")
        print(f"  input_config.extract_formats = {getattr(input_config, 'extract_formats', 'NOT_SET')}")
        print(f"  self.merge_mode = {self.merge_mode}")
        print(f"  self.extract_formats = {self.extract_formats}")

    @classmethod
    def get_project_type(cls):
        return ProjectType.DOCX

    @property
    def support_file(self):
        return 'docx'

    def on_read_source(self, file_path: Path, pre_read_metadata: PreReadMetadata) -> CacheFile:
        """
        固定接口：根据 InputConfig 中的 merge_mode 动态选择行为
        - merge_mode=False：逐run读取（原有逻辑）
        - merge_mode=True：按段落合并读取（便于长文本翻译）
        """
        if self.merge_mode:
            # 合并段落模式
            return self._read_merged_paragraphs(file_path)
        else:
            # 默认逐run模式（原有逻辑）
            return self._read_individual_runs(file_path)

    def _read_individual_runs(self, file_path: Path) -> CacheFile:
        """逐个 run 读取（提取所有 w:t 标签的文本）"""
        items = []
        
        print(f"\n[DocxReader._read_individual_runs]")
        print(f"  文件: {file_path.name}")
        print(f"  merge_mode: {self.merge_mode}")
        
        # 读取正文和脚注
        for xml_name in ['document', 'footnotes']:
            xml_soup = self.file_accessor.read_xml_soup(file_path, xml_name)
            
            if xml_soup is None:
                continue
                
            is_footnote = (xml_name == 'footnotes')
            
            # 提取所有 w:t 标签的文本
            t_tags = xml_soup.find_all('w:t')
            xml_name_items = []
            
            print(f"\n  处理 {xml_name}.xml:")
            print(f"    找到的w:t标签总数: {len(t_tags)}")
            
            for match in t_tags:
                if isinstance(match.string, str) and match.string.strip():
                    text = str(match.string)
                    if text not in ("", "\n", " ", '\xa0'):
                        xml_name_items.append(text)
            
            # 调试信息
            print(f"    有效文本数: {len(xml_name_items)}")
            if xml_name_items:
                print(f"    前3个样本:")
                for i, text in enumerate(xml_name_items[:3], 1):
                    print(f"      {i}. '{text[:50]}'")
            
            # 创建 CacheItem
            extra = {'footnote': 1} if is_footnote else {}
            items.extend(
                CacheItem(source_text=text, extra=extra) 
                for text in xml_name_items
            )
        
        print(f"\n  总共创建 {len(items)} 个 CacheItem")
        return CacheFile(items=items)

    def _read_merged_paragraphs(self, file_path: Path) -> CacheFile:
        """按合并段落读取，每个段落作为一个 CacheItem，可选提取格式信息"""
        items = []
        
        # 使用统一接口读取正文和脚注
        for xml_name in ['document', 'footnotes']:
            paragraph_list = self.file_accessor.read_paragraphs(
                file_path, xml_name=xml_name
            )
            
            if paragraph_list is None:
                continue
                
            is_footnote = (xml_name == 'footnotes')
            extra_base = {'merged': True, 'footnote': 1} if is_footnote else {'merged': True}
            
            # 如果需要提取格式信息
            if self.extract_formats:
                # 读取段落XML以提取格式
                xml_soup = self.file_accessor.read_xml_soup(file_path, xml_name)
                if xml_soup:
                    paragraphs = xml_soup.find_all('w:p')
                    para_count = 0  # 非空段落计数器
                    
                    for xml_index, para in enumerate(paragraphs):  # xml_index 是 XML 中的实际位置
                        # 直接传入 BeautifulSoup Tag 对象，不要转字符串
                        try:
                            pure_text, run_formats = self.format_extractor.extract_from_paragraph(para)
                            
                            if pure_text.strip():
                                # 存储格式信息到extra
                                extra_data = {
                                    **extra_base, 
                                    'para_index': para_count,  # 非空段落的顺序索引
                                    'xml_index': xml_index,    # XML中的实际位置(包括空段落)
                                    'run_formats': run_formats,
                                    'para_xml': str(para)  # 保存原始XML字符串用于后续处理
                                }
                                
                                items.append(CacheItem(
                                    source_text=pure_text,
                                    extra=extra_data
                                ))
                                para_count += 1
                        except Exception as e:
                            # 格式提取失败，回退到普通文本
                            import logging
                            logging.warning(f"格式提取失败: {e}")
                            if para_count < len(paragraph_list) and paragraph_list[para_count].strip():
                                items.append(CacheItem(
                                    source_text=paragraph_list[para_count],
                                    extra={**extra_base, 'para_index': para_count}
                                ))
                                para_count += 1
            else:
                # 普通模式：不提取格式
                items.extend(
                    CacheItem(
                        source_text=para_text, 
                        extra={**extra_base, 'para_index': i}
                    )
                    for i, para_text in enumerate(paragraph_list)
                    if para_text.strip()
                )
        
        print(f"\n[DocxReader._read_merged_paragraphs] 读取完成:")
        print(f"  总段落数: {len(items)}")
        print(f"  正文段落: {sum(1 for item in items if not item.extra.get('footnote'))}")
        print(f"  脚注段落: {sum(1 for item in items if item.extra.get('footnote'))}")
        
        # 显示前几个和最后几个段落的preview
        if items:
            print(f"\n  前3个段落preview:")
            for i, item in enumerate(items[:3], 1):
                print(f"    {i}. {item.source_text[:60]}...")
            print(f"\n  最后3个段落preview:")
            for i, item in enumerate(items[-3:], len(items)-2):
                print(f"    {i}. {item.source_text[:60]}...")
        
        return CacheFile(items=items)
