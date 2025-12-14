"""
格式提取器 - 从Word文档中提取格式信息
与DocxAccessor配合工作，将格式与文本分离
"""
from pathlib import Path
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup
import re

from ModuleFolders.BoundaryMarkerAlternative.position_mapper import RunFormat, FormatMapping


class FormatExtractor:
    """从Word文档XML中提取格式信息"""
    
    def __init__(self):
        pass
    
    def extract_from_paragraph(self, paragraph_xml) -> Tuple[str, List[RunFormat]]:
        """
        从段落XML中提取纯文本和格式信息
        
        Args:
            paragraph_xml: 段落的XML (可以是字符串或 BeautifulSoup Tag 对象)
        
        Returns:
            (纯文本, 格式列表)
        """
        # 如果是字符串，解析为 soup；如果已经是 Tag，直接使用
        if isinstance(paragraph_xml, str):
            soup = BeautifulSoup(paragraph_xml, 'xml')
            para_tag = soup.find('w:p')
        else:
            para_tag = paragraph_xml
        
        pure_text = ""
        run_formats = []
        current_pos = 0
        
        # 遍历所有run
        for run in para_tag.find_all('w:r'):
            # 提取文本
            t_tags = run.find_all('w:t')
            run_text = ''.join(t.get_text() for t in t_tags)
            
            if not run_text:
                continue
            
            # 提取格式
            run_format = self._extract_run_format(run, current_pos, len(run_text))
            
            pure_text += run_text
            run_formats.append(run_format)
            current_pos += len(run_text)
        
        return pure_text, run_formats
    
    def _extract_run_format(self, run_tag, start_pos: int, length: int) -> RunFormat:
        """从w:r标签中提取格式信息"""
        rpr = run_tag.find('w:rPr')
        
        if not rpr:
            # 无格式，返回默认
            return RunFormat(start=start_pos, end=start_pos + length)
        
        # 提取各种格式属性
        bold = rpr.find('w:b') is not None
        italic = rpr.find('w:i') is not None
        underline = rpr.find('w:u') is not None
        
        # 颜色
        color_tag = rpr.find('w:color')
        color = color_tag.get('w:val') if color_tag else None
        
        # 字体
        font_tag = rpr.find('w:rFonts')
        font_name = font_tag.get('w:ascii') if font_tag else None
        
        # 字号
        sz_tag = rpr.find('w:sz')
        font_size = int(sz_tag.get('w:val')) // 2 if sz_tag else None  # Word字号是半磅
        
        # 垂直对齐(上标/下标)
        vert_align_tag = rpr.find('w:vertAlign')
        vert_align = vert_align_tag.get('w:val') if vert_align_tag else None
        
        # 文本位置(上移/下移)
        position_tag = rpr.find('w:position')
        position = int(position_tag.get('w:val')) if position_tag else None
        
        return RunFormat(
            start=start_pos,
            end=start_pos + length,
            bold=bold,
            italic=italic,
            underline=underline,
            color=color,
            font_name=font_name,
            font_size=font_size,
            vert_align=vert_align,
            position=position
        )
    
    def extract_from_marked_text(self, marked_text: str, docx_accessor, file_path: Path, para_index: int) -> Tuple[str, List[RunFormat]]:
        """
        从带边界标记的文本反向提取格式信息
        用于过渡期兼容旧方案
        
        Args:
            marked_text: 带<RUNBND>标记的文本
            docx_accessor: DocxAccessor实例
            file_path: docx文件路径
            para_index: 段落索引
        
        Returns:
            (纯文本, 格式列表)
        """
        # 读取XML获取实际格式
        xml_soup = docx_accessor.read_xml_soup(file_path, 'document')
        paragraphs = xml_soup.find_all('w:p')
        
        if para_index >= len(paragraphs):
            # 索引越界，返回空格式
            clean_text = re.sub(r'<RUNBND\d+>', '', marked_text)
            return clean_text, []
        
        para = paragraphs[para_index]
        return self.extract_from_paragraph(str(para))
    
    def merge_consecutive_formats(self, runs: List[RunFormat]) -> List[RunFormat]:
        """合并连续的相同格式run"""
        if not runs:
            return []
        
        merged = [runs[0]]
        
        for run in runs[1:]:
            last = merged[-1]
            
            # 检查格式是否完全相同且位置连续
            if (last.end == run.start and
                last.bold == run.bold and
                last.italic == run.italic and
                last.underline == run.underline and
                last.color == run.color and
                last.font_name == run.font_name and
                last.font_size == run.font_size):
                # 合并：扩展最后一个run的结束位置
                last.end = run.end
            else:
                # 不同格式，添加新run
                merged.append(run)
        
        return merged


class FormatApplier:
    """将格式信息应用回Word文档"""
    
    def __init__(self):
        pass
    
    def apply_to_paragraph(self, paragraph_xml: str, pure_text: str, run_formats: List[RunFormat]) -> str:
        """
        将格式应用到段落XML
        
        Args:
            paragraph_xml: 原段落XML
            pure_text: 翻译后的纯文本
            run_formats: 要应用的格式列表
        
        Returns:
            新的段落XML
        """
        soup = BeautifulSoup(paragraph_xml, 'xml')
        para = soup.find('w:p')
        
        if not para:
            return paragraph_xml
        
        # 删除所有现有的run
        for run in para.find_all('w:r'):
            run.decompose()
        
        # 根据格式列表创建新的runs
        for run_format in run_formats:
            run_element = self._create_run_element(
                pure_text[run_format.start:run_format.end],
                run_format,
                soup
            )
            para.append(run_element)
        
        return str(soup)
    
    def _create_run_element(self, text: str, run_format: RunFormat, soup):
        """创建带格式的run元素（直接返回Tag对象）"""
        # 创建run标签
        run = soup.new_tag('w:r')
        
        # 创建格式标签
        if any([run_format.bold, run_format.italic, run_format.underline, 
                run_format.color, run_format.font_name, run_format.font_size]):
            rpr = soup.new_tag('w:rPr')
            
            if run_format.bold:
                rpr.append(soup.new_tag('w:b'))
            
            if run_format.italic:
                rpr.append(soup.new_tag('w:i'))
            
            if run_format.underline:
                u_tag = soup.new_tag('w:u')
                u_tag['w:val'] = 'single'
                rpr.append(u_tag)
            
            if run_format.color:
                color_tag = soup.new_tag('w:color')
                color_tag['w:val'] = run_format.color
                rpr.append(color_tag)
            
            if run_format.font_name:
                font_tag = soup.new_tag('w:rFonts')
                font_tag['w:ascii'] = run_format.font_name
                font_tag['w:hAnsi'] = run_format.font_name
                rpr.append(font_tag)
            
            if run_format.font_size:
                sz_tag = soup.new_tag('w:sz')
                sz_tag['w:val'] = str(run_format.font_size * 2)  # 转换为半磅
                rpr.append(sz_tag)
                szcs_tag = soup.new_tag('w:szCs')
                szcs_tag['w:val'] = str(run_format.font_size * 2)
                rpr.append(szcs_tag)
            
            run.append(rpr)
        
        # 创建文本标签
        t_tag = soup.new_tag('w:t')
        t_tag['xml:space'] = 'preserve'
        t_tag.string = text
        run.append(t_tag)
        
        return run


# 使用示例
def demo_format_extraction():
    """演示格式提取和应用"""
    print("=" * 60)
    print("格式提取器演示")
    print("=" * 60)
    
    # 模拟段落XML
    sample_xml = '''
    <w:p>
        <w:r>
            <w:rPr>
                <w:b/>
                <w:color w:val="FF0000"/>
            </w:rPr>
            <w:t>世界</w:t>
        </w:r>
        <w:r>
            <w:rPr>
                <w:i/>
            </w:rPr>
            <w:t>卫生</w:t>
        </w:r>
        <w:r>
            <w:t>组织</w:t>
        </w:r>
    </w:p>
    '''
    
    extractor = FormatExtractor()
    pure_text, run_formats = extractor.extract_from_paragraph(sample_xml)
    
    print(f"纯文本: {pure_text}")
    print(f"格式信息:")
    for i, fmt in enumerate(run_formats):
        print(f"  Run {i+1}: [{fmt.start}:{fmt.end}] '{pure_text[fmt.start:fmt.end]}'")
        print(f"    bold={fmt.bold}, italic={fmt.italic}, color={fmt.color}")
    
    # 应用格式到译文
    target_text = "World Health Organization"
    # 假设格式已通过PositionMapper映射
    target_formats = [
        RunFormat(0, 5, bold=True, color="FF0000"),  # "World"
        RunFormat(6, 12, italic=True),                # "Health"
        RunFormat(13, 25)                             # "Organization"
    ]
    
    applier = FormatApplier()
    new_xml = applier.apply_to_paragraph(sample_xml, target_text, target_formats)
    
    print(f"\n应用格式后的XML:")
    print(new_xml[:200] + "...")
    
    print("=" * 60)


if __name__ == "__main__":
    demo_format_extraction()
