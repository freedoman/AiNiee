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


class DocxReader(BaseSourceReader):
    def __init__(self, input_config: InputConfig):
        super().__init__(input_config)
        # 确保 merge_mode 默认为 True
        if not hasattr(input_config, 'merge_mode'):
            input_config.merge_mode = True
        self.file_accessor = DocxAccessor()

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
        - merge_mode=True（默认）：按段落合并读取（便于长文本翻译）
        """
        merge_mode = getattr(self.input_config, 'merge_mode', True)
        
        if merge_mode:
            # 合并段落模式
            return self._read_merged_paragraphs(file_path)
        else:
            # 默认逐run模式（原有逻辑）
            return self._read_individual_runs(file_path)

    def _read_individual_runs(self, file_path: Path) -> CacheFile:
        """逐个 run 读取（提取所有 w:t 标签的文本）"""
        items = []
        
        # 读取正文和脚注
        for xml_name in ['document', 'footnotes']:
            xml_soup = self.file_accessor.read_xml_soup(file_path, xml_name)
            
            if xml_soup is None:
                continue
                
            is_footnote = (xml_name == 'footnotes')
            
            # 提取所有 w:t 标签的文本
            t_tags = xml_soup.find_all('w:t')
            filtered_texts = (
                match.string for match in t_tags 
                if isinstance(match.string, str) and match.string.strip()
            )
            
            # 创建 CacheItem
            extra = {'footnote': 1} if is_footnote else {}
            items.extend(
                CacheItem(source_text=str(text), extra=extra) 
                for text in filtered_texts
                if text not in ("", "\n", " ", '\xa0')
            )
            
        return CacheFile(items=items)

    def _read_merged_paragraphs(self, file_path: Path) -> CacheFile:
        """按合并段落读取，每个段落作为一个 CacheItem"""
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
            
            # 构建 CacheItem 列表
            items.extend(
                CacheItem(
                    source_text=para_text, 
                    extra={**extra_base, 'para_index': i}
                )
                for i, para_text in enumerate(paragraph_list)
                if para_text.strip()
            )
        
        return CacheFile(items=items)
