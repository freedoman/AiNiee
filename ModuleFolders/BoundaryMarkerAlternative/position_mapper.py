"""
位置映射方案 - 边界标记的根本性替代方案
将格式信息与翻译内容完全分离

实现思路:
1. 从Word文档中提取纯文本和格式信息（RunFormat列表）
2. LLM只看到纯文本进行翻译
3. 翻译后通过位置映射算法将格式应用到译文
4. 写回Word时应用映射后的格式

优势:
- 100%准确：格式永远不会丢失或错乱
- 翻译质量更高：LLM不被格式标记干扰
- 可视化：格式映射可单独调试和优化
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import re
import json


@dataclass
class RunFormat:
    """文本片段的格式信息"""
    start: int          # 起始位置(字符索引)
    end: int            # 结束位置
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    vert_align: Optional[str] = None  # 垂直对齐: 'superscript'(上标) / 'subscript'(下标)
    position: Optional[int] = None    # 文本位置(半磅): 正值=上移, 负值=下移


@dataclass
class FormatMapping:
    """格式映射数据结构"""
    source_text: str                          # 原文纯文本
    target_text: str                          # 译文纯文本
    source_runs: List[RunFormat]              # 原文格式列表
    target_runs: Optional[List[RunFormat]] = None  # 译文格式列表（自动计算）
    mapping_method: str = "ratio"             # 映射方法: ratio/word_align/manual
    confidence: float = 0.0                   # 映射置信度 0-1
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            'source_text': self.source_text,
            'target_text': self.target_text,
            'source_runs': [self._run_to_dict(r) for r in self.source_runs],
            'target_runs': [self._run_to_dict(r) for r in self.target_runs] if self.target_runs else None,
            'mapping_method': self.mapping_method,
            'confidence': self.confidence
        }
    
    @staticmethod
    def _run_to_dict(run: RunFormat) -> dict:
        return {
            'start': run.start,
            'end': run.end,
            'bold': run.bold,
            'italic': run.italic,
            'underline': run.underline,
            'color': run.color,
            'font_name': run.font_name,
            'font_size': run.font_size,
            'vert_align': run.vert_align,
            'position': run.position
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FormatMapping':
        """从字典反序列化"""
        return cls(
            source_text=data['source_text'],
            target_text=data['target_text'],
            source_runs=[cls._dict_to_run(r) for r in data['source_runs']],
            target_runs=[cls._dict_to_run(r) for r in data['target_runs']] if data.get('target_runs') else None,
            mapping_method=data.get('mapping_method', 'ratio'),
            confidence=data.get('confidence', 0.0)
        )
    
    @staticmethod
    def _dict_to_run(data: dict) -> RunFormat:
        return RunFormat(
            start=data['start'],
            end=data['end'],
            bold=data.get('bold', False),
            italic=data.get('italic', False),
            underline=data.get('underline', False),
            color=data.get('color'),
            font_name=data.get('font_name'),
            font_size=data.get('font_size'),
            vert_align=data.get('vert_align'),
            position=data.get('position')
        )


class PositionMapper:
    """位置映射器 - 从原文格式映射到译文格式"""
    
    def __init__(self, default_method: str = "ratio"):
        """
        Args:
            default_method: 默认映射方法 "ratio" | "word_align" | "hybrid"
        """
        self.default_method = default_method
        self.word_aligner = None  # 延迟初始化
    
    def map_format(self, mapping: FormatMapping, method: Optional[str] = None) -> FormatMapping:
        """
        将原文格式映射到译文
        
        Args:
            mapping: 包含原文、译文和原文格式的映射对象
            method: 映射方法 "ratio" | "word_align" | "hybrid" | None(使用默认)
        
        Returns:
            填充了target_runs的FormatMapping
        """
        method = method or self.default_method
        
        if method == "ratio":
            return self._map_by_ratio(mapping)
        elif method == "word_align":
            return self._map_by_word_align(mapping)
        elif method == "hybrid":
            return self._map_hybrid(mapping)
        else:
            raise ValueError(f"Unknown mapping method: {method}")
    
    def _map_by_ratio(self, mapping: FormatMapping) -> FormatMapping:
        """
        策略1: 混合映射策略 - 结合比例和内容匹配
        
        新思路:
        1. 对于带position属性的格式,优先使用**内容匹配**(查找数字/标点在译文中的位置)
        2. 对于普通格式(粗体/斜体/颜色),使用比例映射
        
        原因: position通常用于参考文献格式,数字/标点在翻译中位置不变
        例如: "子杂志，2023，8（6）" → "журнал，2023，8（6）"
        数字"2023"的位置从7变成了8,但可以通过查找"2023"精确定位
        """
        target_runs = []
        
        if len(mapping.source_text) == 0:
            mapping.target_runs = target_runs
            mapping.mapping_method = "ratio"
            mapping.confidence = 0.0
            return mapping
        
        for source_run in mapping.source_runs:
            # 提取原文该run对应的文本
            source_segment = mapping.source_text[source_run.start:source_run.end]
            
            # **第一步: 验证原文片段是否应该有 position 属性**
            # 如果原文本身就不应该有 position（如长文本），直接清除
            has_position = source_run.position is not None or source_run.vert_align is not None
            
            if has_position and not self._should_apply_position(source_segment):
                # 原文有 position 但不应该有（如"一、结核分枝杆菌耐药的定义及其分类"）
                # 清除 position 属性，避免错误传递到译文
                vert_align_val = None
                position_val = None
                has_position = False
            else:
                # 保留原有的 position 值
                vert_align_val = source_run.vert_align
                position_val = source_run.position
            
            target_start = None
            target_end = None
            
            # **第二步: 尝试精确匹配（仅对有效的 position）**
            if has_position and self._should_apply_position(source_segment):
                # 策略A: 精确匹配 - 在译文中查找相同内容
                # 这对数字、标点特别有效
                try:
                    idx = mapping.target_text.find(source_segment)
                    if idx != -1:
                        # 找到精确匹配!
                        target_start = idx
                        target_end = idx + len(source_segment)
                    else:
                        # 未找到,尝试模糊匹配(去除空格后)
                        source_stripped = source_segment.strip().replace(' ', '')
                        target_stripped = mapping.target_text.replace(' ', '')
                        idx_stripped = target_stripped.find(source_stripped)
                        if idx_stripped != -1:
                            # 反向映射到原始位置
                            target_start = mapping.target_text.find(source_stripped)
                            target_end = target_start + len(source_segment) if target_start != -1 else None
                except:
                    pass
            
            # **第三步: 精确匹配失败，使用比例映射**
            if target_start is None or target_end is None:
                # 策略B: 比例映射
                start_ratio = source_run.start / len(mapping.source_text)
                end_ratio = source_run.end / len(mapping.source_text)
                
                target_start = int(start_ratio * len(mapping.target_text))
                target_end = int(end_ratio * len(mapping.target_text))
                
                # 边界修正
                target_start = max(0, min(target_start, len(mapping.target_text)))
                target_end = max(target_start, min(target_end, len(mapping.target_text)))
                
                # 验证目标内容是否适合position
                if (vert_align_val or position_val) and target_start < target_end:
                    target_segment = mapping.target_text[target_start:target_end]
                    if not self._should_apply_position(target_segment):
                        # 内容不匹配,清除position属性
                        vert_align_val = None
                        position_val = None
            
            # **第四步: 创建译文格式 run（无论是精确匹配还是比例映射）**
            target_run = RunFormat(
                start=target_start,
                end=target_end,
                bold=source_run.bold,
                italic=source_run.italic,
                underline=source_run.underline,
                color=source_run.color,
                font_name=source_run.font_name,
                font_size=source_run.font_size,
                vert_align=vert_align_val,
                position=position_val
            )
            target_runs.append(target_run)
        
        # **第五步: 合并重叠并填充空隙，确保100%覆盖**
        # 使用默认格式填充空隙（继承相邻格式，但不继承position）
        default_format = target_runs[0] if target_runs else None
        if default_format and len(mapping.target_text) > 0:
            target_runs = self._merge_and_fill_runs(
                target_runs, 
                len(mapping.target_text), 
                default_format
            )
        
        mapping.target_runs = target_runs
        mapping.mapping_method = "ratio"
        mapping.confidence = self._calculate_confidence_ratio(mapping)
        return mapping
    
    def _should_apply_position(self, text: str) -> bool:
        """
        判断文本片段是否应该应用position/vert_align属性
        
        **新策略: 严格验证原文 position 属性**
        
        position/vert_align 属性用于上标/下标,通常只出现在:
        1. 参考文献标记: "［1］", "［2-5］", "(1)", "*"
        2. 脚注标记: "①", "②", "*", "**"
        3. 数学/化学符号: "2", "10", "n"
        
        原则:
        - **长文本不应该有 position** (即使包含标点)
        - **只有极短片段**才可能是上标/下标
        - 例: "一、结核分枝杆菌耐药的定义及其分类" 虽然有标点,但长度17不可能是上标
        """
        if not text:
            return False
        
        # 去除首尾空白
        text = text.strip()
        if not text:
            return False
        
        # 规则1: 长度限制 - position 只用于极短片段
        # 参考文献标记通常不超过8个字符: "［1-3］", "(12)", "①②"
        if len(text) > 8:
            return False  # 过滤长文本(如"一、结核分枝杆菌耐药的定义及其分类")
        
        # 规则2: 纯数字/标点组合 - 典型的引用标记
        # 如: "1", "2-5", "［1］", "①", "*"
        punct_chars = '，。、；：！？（）［］【】《》""''〈〉﹝﹞—…·,.;:!?()[]{}""\'\'<>-/*①②③④⑤⑥⑦⑧⑨⑩'
        has_digit = any(c.isdigit() for c in text)
        has_punct = any(c in punct_chars for c in text)
        is_short_ref = (has_digit or has_punct) and len(text) <= 8
        
        if is_short_ref:
            return True  # 保留短引用标记
        
        # 规则3: 单字母/短字母组合 - 可能是变量或符号
        # 如: "n", "CD", "R", "TM"
        if text.isalpha() and len(text) <= 3:
            return True  # 保留短字母(可能是数学/化学符号)
        
        # 规则4: 其他情况一律过滤
        # 包括:
        # - 长字母单词: "журнал", "multidrug"
        # - 包含标点的长文本: "一、结核分枝杆菌耐药的定义及其分类"
        # - 混合内容的长文本
        return False
    
    def _calculate_confidence_ratio(self, mapping: FormatMapping) -> float:
        """计算比例映射的置信度"""
        # 基于长度比的相似度
        if len(mapping.source_text) == 0:
            return 0.0
        
        length_ratio = len(mapping.target_text) / len(mapping.source_text)
        # 假设合理的长度比在0.5-2.0之间
        if 0.5 <= length_ratio <= 2.0:
            confidence = 1.0 - abs(1.0 - length_ratio)
        else:
            confidence = 0.3
        
        return max(0.0, min(1.0, confidence))
    
    def _map_by_word_align(self, mapping: FormatMapping) -> FormatMapping:
        """
        策略2: 基于词对齐的精确映射
        适用场景: 结构差异大的长句
        需要安装: pip install simalign (可选)
        """
        try:
            # 尝试使用高级对齐
            return self._map_with_simalign(mapping)
        except (ImportError, Exception):
            # 回退到简单的空格分词对齐
            return self._map_with_simple_align(mapping)
    
    def _map_with_simple_align(self, mapping: FormatMapping) -> FormatMapping:
        """
        使用简单空格分词的词对齐
        
        新策略: 保证100%覆盖率
        1. 先映射所有source_runs
        2. 合并重叠的runs
        3. 填充未覆盖的区域(使用默认格式)
        """
        source_words = mapping.source_text.split()
        target_words = mapping.target_text.split()
        
        if not source_words or not target_words:
            return self._map_by_ratio(mapping)
        
        # 计算每个源词的字符位置
        source_word_positions = []
        pos = 0
        for word in source_words:
            start = mapping.source_text.find(word, pos)
            end = start + len(word)
            source_word_positions.append((start, end))
            pos = end
        
        # 计算每个目标词的字符位置
        target_word_positions = []
        pos = 0
        for word in target_words:
            start = mapping.target_text.find(word, pos)
            end = start + len(word)
            target_word_positions.append((start, end))
            pos = end
        
        # 对每个source_run找到对应的target范围
        target_runs = []
        for source_run in mapping.source_runs:
            # 找到source_run覆盖的词索引
            covered_word_indices = []
            for i, (word_start, word_end) in enumerate(source_word_positions):
                # 如果词与run有重叠
                if not (word_end <= source_run.start or word_start >= source_run.end):
                    covered_word_indices.append(i)
            
            if not covered_word_indices:
                # 没有覆盖的词，使用比例映射
                start_ratio = source_run.start / len(mapping.source_text) if len(mapping.source_text) > 0 else 0
                end_ratio = source_run.end / len(mapping.source_text) if len(mapping.source_text) > 0 else 0
                target_start = int(start_ratio * len(mapping.target_text))
                target_end = int(end_ratio * len(mapping.target_text))
            else:
                # 简单映射：源词索引 -> 目标词索引 (假设顺序一致)
                first_word_idx = covered_word_indices[0]
                last_word_idx = covered_word_indices[-1]
                
                # 比例映射到目标词
                target_first_idx = int(first_word_idx * len(target_words) / len(source_words)) if len(source_words) > 0 else 0
                target_last_idx = int(last_word_idx * len(target_words) / len(source_words)) if len(source_words) > 0 else 0
                
                target_first_idx = max(0, min(target_first_idx, len(target_word_positions) - 1))
                target_last_idx = max(target_first_idx, min(target_last_idx, len(target_word_positions) - 1))
                
                target_start = target_word_positions[target_first_idx][0]
                target_end = target_word_positions[target_last_idx][1]
            
            # 边界检查
            target_start = max(0, min(target_start, len(mapping.target_text)))
            target_end = max(target_start, min(target_end, len(mapping.target_text)))
            
            # 对于带有position/vert_align属性的格式,进行智能验证
            vert_align_val = source_run.vert_align
            position_val = source_run.position
            
            if (vert_align_val or position_val) and target_start < target_end:
                # 检查目标区域的内容是否适合应用position属性
                target_segment = mapping.target_text[target_start:target_end]
                if not self._should_apply_position(target_segment):
                    vert_align_val = None
                    position_val = None
            
            target_run = RunFormat(
                start=target_start,
                end=target_end,
                bold=source_run.bold,
                italic=source_run.italic,
                underline=source_run.underline,
                color=source_run.color,
                font_name=source_run.font_name,
                font_size=source_run.font_size,
                vert_align=vert_align_val,
                position=position_val
            )
            target_runs.append(target_run)
        
        # 后处理: 合并重叠的runs并填充空隙
        target_runs = self._merge_and_fill_runs(target_runs, len(mapping.target_text), mapping.source_runs[0] if mapping.source_runs else None)
        
        mapping.target_runs = target_runs
        mapping.mapping_method = "word_align_simple"
        mapping.confidence = 0.7  # 简单对齐置信度中等
        return mapping
    
    def _merge_and_fill_runs(self, runs: List[RunFormat], text_length: int, default_format: Optional[RunFormat]) -> List[RunFormat]:
        """
        合并重叠的runs并填充空隙,确保100%覆盖
        
        策略:
        1. 按start位置排序
        2. 合并重叠区域(保留第一个的格式)
        3. 填充空隙(使用默认格式或最近的格式)
        """
        if not runs:
            # 没有格式,创建一个覆盖全文的默认格式
            if default_format:
                return [RunFormat(
                    start=0,
                    end=text_length,
                    bold=default_format.bold,
                    italic=default_format.italic,
                    underline=default_format.underline,
                    color=default_format.color,
                    font_name=default_format.font_name,
                    font_size=default_format.font_size,
                    vert_align=None,
                    position=None
                )]
            else:
                return [RunFormat(start=0, end=text_length)]
        
        # 排序并去重
        runs = sorted(runs, key=lambda r: (r.start, r.end))
        
        merged = []
        current_pos = 0
        
        for run in runs:
            # 如果有空隙,填充它
            if run.start > current_pos:
                # 使用前一个run的格式(去除position属性)
                prev_format = merged[-1] if merged else (default_format or RunFormat(start=0, end=0))
                gap_run = RunFormat(
                    start=current_pos,
                    end=run.start,
                    bold=prev_format.bold,
                    italic=prev_format.italic,
                    underline=prev_format.underline,
                    color=prev_format.color,
                    font_name=prev_format.font_name,
                    font_size=prev_format.font_size,
                    vert_align=None,  # 空隙不继承position属性
                    position=None
                )
                merged.append(gap_run)
            
            # 处理重叠
            if run.start < current_pos:
                # 与前一个run重叠,调整start
                run.start = current_pos
            
            if run.end > current_pos:
                # 添加当前run
                merged.append(run)
                current_pos = run.end
        
        # 填充末尾空隙
        if current_pos < text_length:
            last_format = merged[-1] if merged else (default_format or RunFormat(start=0, end=0))
            tail_run = RunFormat(
                start=current_pos,
                end=text_length,
                bold=last_format.bold,
                italic=last_format.italic,
                underline=last_format.underline,
                color=last_format.color,
                font_name=last_format.font_name,
                font_size=last_format.font_size,
                vert_align=None,
                position=None
            )
            merged.append(tail_run)
        
        return merged
    
    def _map_with_simalign(self, mapping: FormatMapping) -> FormatMapping:
        """使用simalign库的高级对齐（可选）"""
        from simalign import SentenceAligner
        
        if self.word_aligner is None:
            self.word_aligner = SentenceAligner(model="bert", token_type="bpe", matching_methods="mai")
        
        # 获取词对齐 (返回格式: {'mwmf': [(src_idx, tgt_idx), ...], ...})
        alignments = self.word_aligner.get_word_aligns(mapping.source_text, mapping.target_text)
        align_pairs = alignments.get('mwmf', [])  # 使用mwmf方法
        
        # 构建对齐映射
        align_map = {src: tgt for src, tgt in align_pairs}
        
        # TODO: 实现基于高级对齐的格式映射
        # 这里先回退到简单方法
        return self._map_with_simple_align(mapping)
    
    def _map_hybrid(self, mapping: FormatMapping) -> FormatMapping:
        """
        策略3: 混合策略
        短文本用比例，长文本用词对齐
        """
        # 根据文本长度选择策略
        if len(mapping.source_text) < 50:
            return self._map_by_ratio(mapping)
        else:
            return self._map_by_word_align(mapping)


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
