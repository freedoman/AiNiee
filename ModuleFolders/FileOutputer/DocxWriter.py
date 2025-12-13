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
        """逐个 run 写入（原有逻辑保持不变）"""
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

        # 处理脚注内容，如果有的话
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
        
        # 写入翻译结果到新的文件            
        self.file_accessor.write_content(
            content, footnotes, translation_file_path, source_file_path
        )

    def _write_merged_paragraphs(
        self, translation_file_path: Path, cache_file: CacheFile, source_file_path: Path = None
    ):
        """按合并段落写入翻译结果"""
        # 重新读取 metadata（Writer 和 Reader 是独立实例）
        # skip_simplify=True: Reader 已经简化过源文件，无需重复简化
        _, run_mapping, xml_soup = self.file_accessor.read_paragraphs(
            source_file_path, with_mapping=True, skip_simplify=True
        )
        
        # 提取翻译后的段落列表
        translated_paragraphs = [
            item.final_text for item in cache_file.items 
            if item.extra.get('merged')
        ]
        
        # 将译文写回到 XML DOM（通过修改 run_mapping 中的 tags，自动修改 xml_soup）
        self.file_accessor.write_paragraphs(run_mapping, translated_paragraphs)
        
        # 写入文件（xml_soup 已被 write_paragraphs 修改）
        from ModuleFolders.FileAccessor import ZipUtil
        ZipUtil.replace_in_zip_file(
            source_file_path, translation_file_path, 
            {"word/document.xml": str(xml_soup)}
        )

    @classmethod
    def get_project_type(self):
        return ProjectType.DOCX
