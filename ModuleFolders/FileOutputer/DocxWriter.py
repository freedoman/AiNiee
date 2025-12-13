from pathlib import Path

from ModuleFolders.Cache.CacheFile import CacheFile
from ModuleFolders.Cache.CacheProject import ProjectType
from ModuleFolders.FileAccessor.DocxAccessor import DocxAccessor
from ModuleFolders.FileOutputer.BaseWriter import (
    BaseTranslatedWriter,
    OutputConfig,
    PreWriteMetadata
)


class DocxWriter(BaseTranslatedWriter):
    def __init__(self, output_config: OutputConfig):
        super().__init__(output_config)
        # 确保 merge_mode 默认为 True
        if not hasattr(output_config, 'merge_mode'):
            output_config.merge_mode = True
        self.file_accessor = DocxAccessor()

    def on_write_translated(
        self, translation_file_path: Path, cache_file: CacheFile,
        pre_write_metadata: PreWriteMetadata,
        source_file_path: Path = None,
    ):
        """
        固定接口：根据 OutputConfig 中的 merge_mode 动态选择行为
        - merge_mode=False：逐run写入（原有逻辑）
        - merge_mode=True（默认）：按段落合并写入（需与 Reader 的 merge_mode=True 配套使用）
        """
        merge_mode = getattr(self.output_config, 'merge_mode', True)
        
        if merge_mode:
            # 合并段落模式
            self._write_merged_paragraphs(translation_file_path, cache_file, source_file_path)
        else:
            # 默认逐run模式（原有逻辑）
            self._write_individual_runs(translation_file_path, cache_file, source_file_path)

    def _write_individual_runs(
        self, translation_file_path: Path, cache_file: CacheFile, source_file_path: Path = None
    ):
        """逐个 run 写入（修改所有 w:t 标签）"""
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
            
            # 遍历所有 w:t 标签并替换
            start_index = 0
            for match in xml_soup.find_all("w:t"):
                if isinstance(match.string, str) and match.string.strip():
                    # 查找匹配的翻译项
                    for content_index in range(start_index, len(items)):
                        if match.string == items[content_index].source_text:
                            match.string = items[content_index].final_text
                            start_index = content_index + 1
                            break
            
            files_to_replace[f"word/{xml_name}.xml"] = str(xml_soup)
        
        self._write_files_to_docx(source_file_path, translation_file_path, files_to_replace)

    def _write_merged_paragraphs(
        self, translation_file_path: Path, cache_file: CacheFile, source_file_path: Path = None
    ):
        """按合并段落写入翻译结果，支持正文和脚注"""
        files_to_replace = {}
        
        # 处理正文和脚注
        for xml_name in ['document', 'footnotes']:
            result = self.file_accessor.read_paragraphs(
                source_file_path, xml_name=xml_name, 
                with_mapping=True, skip_simplify=True
            )
            if result is None:
                continue
                
            _, run_mapping, xml_soup = result
            is_footnote = (xml_name == 'footnotes')
            
            # 提取对应的翻译段落
            translated_paragraphs = [
                item.final_text for item in cache_file.items
                if item.extra.get('merged') and 
                   bool(item.extra.get('footnote')) == is_footnote
            ]
            
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
