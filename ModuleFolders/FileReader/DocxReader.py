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
        self.merged_text_metadata = None

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
        """逐个 run 读取（原有逻辑保持不变）"""
        xml_soup = self.file_accessor.read_content(file_path)
        paragraphs = xml_soup.find_all('w:t')
        # 过滤掉空的内容
        filtered_matches = (match.string for match in paragraphs if isinstance(match.string, str) and match.string.strip())
        items = [
            CacheItem(source_text=str(text)) for text in filtered_matches
            if not (text == "" or text == "\n" or text == " " or text == '\xa0')
        ]
        
        # 读取脚注内容，如果有的话
        xml_soup_footnotes = self.file_accessor.read_footnotes(file_path)
        if xml_soup_footnotes:
            footnotes = xml_soup_footnotes.find_all('w:t')
            filtered_matches_footnotes = (match.string for match in footnotes if isinstance(match.string, str) and match.string.strip())
            items.extend(
                CacheItem(source_text=str(text), extra={'footnote': 1}) for text in filtered_matches_footnotes
                if not (text == "" or text == "\n" or text == " " or text == '\xa0')
            )
            
        # 返回缓存文件对象
        return CacheFile(items=items)

    def _read_merged_paragraphs(self, file_path: Path) -> CacheFile:
        """按合并段落读取，每个段落作为一个 CacheItem"""
        merged_text, run_mapping, xml_soup = self.file_accessor.read_and_get_runs(file_path)
        
        # 保存元数据供后续写入
        self.merged_text_metadata = {
            'file_path': file_path,
            'xml_soup': xml_soup,
            'run_mapping': run_mapping
        }
        
        # 构建 CacheItem 列表
        items = [
            CacheItem(source_text=para_text, extra={'para_index': i, 'merged': True})
            for i, para_text in enumerate(merged_text.split('\n'))
            if para_text.strip()
        ]
        return CacheFile(items=items)
