"""
位置映射方案 - 边界标记的根本性替代方案
将格式信息与翻译内容完全分离
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import re


@dataclass
class RunFormat:
    """文本片段的格式信息"""
    start: int          # 起始位置（字符索引）
    end: int            # 结束位置
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = None


@dataclass
class FormatMapping:
    """格式映射数据结构"""
    source_text: str                    # 原文纯文本
    target_text: str                    # 译文纯文本
    source_runs: List[RunFormat]        # 原文格式列表
    target_runs: List[RunFormat] = None # 译文格式列表（自动计算）


class PositionMapper:
    """位置映射器 - 从原文格式映射到译文格式"""
    
    def __init__(self):
        pass
    
    def map_format(self, mapping: FormatMapping) -> FormatMapping:
        """
        将原文格式映射到译文
        
        Args:
            mapping: 包含原文、译文和原文格式的映射对象
        
        Returns:
            填充了target_runs的FormatMapping
        """
        # 使用多种策略进行格式映射
        target_runs = []
        
        # 策略1: 基于位置比例的简单映射
        if len(mapping.source_text) > 0:
            for source_run in mapping.source_runs:
                # 计算该run在原文中的位置比例
                start_ratio = source_run.start / len(mapping.source_text)
                end_ratio = source_run.end / len(mapping.source_text)
                
                # 映射到译文
                target_start = int(start_ratio * len(mapping.target_text))
                target_end = int(end_ratio * len(mapping.target_text))
                
                # 创建译文格式
                target_run = RunFormat(
                    start=target_start,
                    end=target_end,
                    bold=source_run.bold,
                    italic=source_run.italic,
                    underline=source_run.underline,
                    color=source_run.color,
                    font_name=source_run.font_name,
                    font_size=source_run.font_size
                )
                target_runs.append(target_run)
        
        mapping.target_runs = target_runs
        return mapping
    
    def map_format_advanced(self, mapping: FormatMapping) -> FormatMapping:
        """
        高级格式映射 - 使用词对齐算法
        需要安装: pip install simalign
        """
        try:
            from simalign import SentenceAligner
            
            # 初始化对齐器
            aligner = SentenceAligner(model="bert", token_type="bpe", matching_methods="mai")
            
            # 获取词对齐
            alignments = aligner.get_word_aligns(mapping.source_text, mapping.target_text)
            
            # 根据对齐结果映射格式
            target_runs = []
            for source_run in mapping.source_runs:
                # 找到source_run覆盖的源词
                # 通过对齐找到对应的目标词
                # 创建target_run
                
                # TODO: 实现详细的对齐逻辑
                pass
            
            mapping.target_runs = target_runs
            return mapping
            
        except ImportError:
            # 如果没有安装simalign，回退到简单映射
            return self.map_format(mapping)


class BoundaryMarkerConverter:
    """将现有的边界标记方案转换为位置映射方案"""
    
    def from_marked_text(self, marked_text: str) -> Tuple[str, List[RunFormat]]:
        """
        从带标记的文本中提取纯文本和格式信息
        
        Args:
            marked_text: 带<RUNBND>标记的文本
        
        Returns:
            (纯文本, 格式列表)
        """
        # 提取所有标记及其位置
        marker_positions = []
        for match in re.finditer(r'<RUNBND\d+>', marked_text):
            marker_positions.append((match.group(), match.start()))
        
        # 移除标记得到纯文本
        clean_text = re.sub(r'<RUNBND\d+>', '', marked_text)
        
        # 根据标记位置生成格式信息
        # 假设每两个连续标记之间是一个格式run
        runs = []
        clean_pos = 0
        
        for i in range(0, len(marker_positions)-1, 2):
            marker1, pos1 = marker_positions[i]
            marker2, pos2 = marker_positions[i+1]
            
            # 计算在纯文本中的位置
            start_clean = self._marked_to_clean_pos(marked_text, pos1 + len(marker1))
            end_clean = self._marked_to_clean_pos(marked_text, pos2)
            
            # 创建run（默认格式，实际应从Word文档中读取）
            run = RunFormat(
                start=start_clean,
                end=end_clean,
                bold=False,
                italic=False
            )
            runs.append(run)
        
        return clean_text, runs
    
    def to_marked_text(self, clean_text: str, runs: List[RunFormat]) -> str:
        """
        将纯文本和格式信息转换回带标记的文本
        （用于向后兼容）
        
        Args:
            clean_text: 纯文本
            runs: 格式列表
        
        Returns:
            带<RUNBND>标记的文本
        """
        # 收集所有需要插入标记的位置
        marker_positions = []
        for i, run in enumerate(runs):
            marker_num = i * 2 + 1
            marker_positions.append((run.start, f'<RUNBND{marker_num}>'))
            marker_positions.append((run.end, f'<RUNBND{marker_num+1}>'))
        
        # 按位置排序
        marker_positions.sort(key=lambda x: x[0])
        
        # 从后往前插入标记（避免位置偏移）
        marked_text = clean_text
        for pos, marker in reversed(marker_positions):
            marked_text = marked_text[:pos] + marker + marked_text[pos:]
        
        return marked_text
    
    def _marked_to_clean_pos(self, marked_text: str, marked_pos: int) -> int:
        """将带标记文本的位置转换为纯文本位置"""
        clean_pos = 0
        for i in range(marked_pos):
            if not re.match(r'<RUNBND\d+>', marked_text[i:]):
                clean_pos += 1
            elif marked_text[i] == '<':
                # 跳过标记
                match = re.match(r'<RUNBND\d+>', marked_text[i:])
                if match:
                    i += len(match.group()) - 1
        return clean_pos


# 使用示例
def demo_position_mapping():
    """演示位置映射方案"""
    
    print("=" * 60)
    print("位置映射方案演示")
    print("=" * 60)
    
    # 场景：从Word中读取的原文
    source_text = "世界卫生组织"
    source_runs = [
        RunFormat(start=0, end=2, bold=True),      # "世界" 加粗
        RunFormat(start=2, end=4, italic=True),    # "卫生" 斜体
        RunFormat(start=4, end=6, color="red")     # "组织" 红色
    ]
    
    # LLM翻译（只看到纯文本）
    target_text = "Всемирная организация здравоохранения"
    
    # 创建映射
    mapping = FormatMapping(
        source_text=source_text,
        target_text=target_text,
        source_runs=source_runs
    )
    
    # 执行格式映射
    mapper = PositionMapper()
    result = mapper.map_format(mapping)
    
    print(f"\n原文: {source_text}")
    print(f"原文格式:")
    for run in result.source_runs:
        print(f"  [{run.start}:{run.end}] {source_text[run.start:run.end]} "
              f"- bold={run.bold}, italic={run.italic}, color={run.color}")
    
    print(f"\n译文: {target_text}")
    print(f"映射后的格式:")
    for run in result.target_runs:
        print(f"  [{run.start}:{run.end}] {target_text[run.start:run.end]} "
              f"- bold={run.bold}, italic={run.italic}, color={run.color}")
    
    print("\n" + "=" * 60)
    print("优势:")
    print("  ✅ LLM只处理纯文本，翻译质量更高")
    print("  ✅ 不会出现标记丢失或顺序错误")
    print("  ✅ 格式映射可以单独调试和优化")
    print("  ✅ 支持可视化编辑格式映射")
    print("=" * 60)


def demo_converter():
    """演示从旧方案转换到新方案"""
    
    print("\n" + "=" * 60)
    print("边界标记转换器演示")
    print("=" * 60)
    
    converter = BoundaryMarkerConverter()
    
    # 旧方案的文本
    marked_text = "<RUNBND1>世界<RUNBND2>卫生<RUNBND3>组织<RUNBND4>"
    
    # 转换为新方案
    clean_text, runs = converter.from_marked_text(marked_text)
    
    print(f"\n旧方案文本: {marked_text}")
    print(f"新方案纯文本: {clean_text}")
    print(f"新方案格式:")
    for i, run in enumerate(runs):
        print(f"  Run {i+1}: [{run.start}:{run.end}] {clean_text[run.start:run.end]}")
    
    # 转换回旧方案（向后兼容）
    marked_back = converter.to_marked_text(clean_text, runs)
    print(f"\n转换回旧方案: {marked_back}")
    print(f"是否一致: {marked_text == marked_back}")
    
    print("=" * 60)


if __name__ == "__main__":
    demo_position_mapping()
    demo_converter()
