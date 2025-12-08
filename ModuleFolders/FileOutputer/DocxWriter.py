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
        self.file_accessor = DocxAccessor()

    def on_write_translated(
        self, translation_file_path: Path, cache_file: CacheFile,
        pre_write_metadata: PreWriteMetadata,
        source_file_path: Path = None,
    ):
        content = self.file_accessor.read_content(source_file_path)
        start_index = 0
        # 根据 w:t 标签找到原文
        paragraphs = content.find_all("w:t")
        content_items = [ item for item in cache_file.items if not item.extra.get('footnote')]
        for match in paragraphs:
            if isinstance(match.string, str) and match.string.strip():
                # 在翻译结果中查找是否存在原文，存在则替换并右移开始下标
                for content_index in range(start_index, len(content_items)):
                    if match.string == content_items[content_index].source_text:
                        match.string = content_items[content_index].final_text
                        start_index = content_index + 1
                        break

        
        footnotes = self.file_accessor.read_footnotes(source_file_path)
        if footnotes:
            start_index = 0
            # 根据 w:t 标签找到原文
            paragraphs = footnotes.find_all("w:t")
            footnotes_items = [ item for item in cache_file.items if item.extra.get('footnote')]
            for match in paragraphs:
                if isinstance(match.string, str) and match.string.strip():
                    # 在翻译结果中查找是否存在原文，存在则替换并右移开始下标
                    for content_index in range(start_index, len(footnotes_items)):
                        if match.string == footnotes_items[content_index].source_text:
                            match.string = footnotes_items[content_index].final_text
                            start_index = content_index + 1
                            break
                    
        self.file_accessor.write_content(
            content, footnotes, translation_file_path, source_file_path
        )
        

    @classmethod
    def get_project_type(self):
        return ProjectType.DOCX
