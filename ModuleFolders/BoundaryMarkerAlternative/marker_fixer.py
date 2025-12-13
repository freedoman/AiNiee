"""
边界标记智能修复模块
提供多种策略自动修复翻译中的标记错误
"""
import re
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher


class BoundaryMarkerFixer:
    """边界标记智能修复器"""
    
    def __init__(self, max_missing: int = 3):
        self.max_missing = max_missing
    
    def fix_markers(self, source_text: str, target_text: str) -> Tuple[bool, str, str]:
        """
        智能修复译文中的标记错误
        
        Args:
            source_text: 原文（带标记）
            target_text: 译文（可能有错误）
        
        Returns:
            (是否修复成功, 修复后的文本, 修复说明)
        """
        source_markers = self._extract_markers(source_text)
        target_markers = self._extract_markers(target_text)
        
        # 诊断问题类型
        missing = set(source_markers) - set(target_markers)
        extra = set(target_markers) - set(source_markers)
        order_wrong = self._check_order(source_markers, target_markers)
        
        # 策略1: 处理标记丢失（末尾标记最容易丢）
        if missing and not extra:
            if len(missing) <= self.max_missing:
                return self._fix_missing_markers(source_text, target_text, missing)
        
        # 策略2: 处理顺序错误（语序调整导致）
        if order_wrong and not missing and not extra:
            return self._fix_marker_order(source_text, target_text)
        
        # 策略3: 混合问题（既有丢失又有顺序错误）
        if missing and order_wrong:
            return self._fix_complex_errors(source_text, target_text, missing)
        
        return False, target_text, "无法自动修复"
    
    def _extract_markers(self, text: str) -> List[str]:
        """提取所有边界标记"""
        return re.findall(r'<RUNBND\d+>', text)
    
    def _extract_marker_positions(self, text: str) -> List[Tuple[str, int]]:
        """提取标记及其位置"""
        markers = []
        for match in re.finditer(r'<RUNBND\d+>', text):
            markers.append((match.group(), match.start()))
        return markers
    
    def _check_order(self, source_markers: List[str], target_markers: List[str]) -> bool:
        """检查标记顺序是否错误"""
        if len(source_markers) != len(target_markers):
            return False
        
        # 提取编号并比较顺序
        source_nums = [int(re.search(r'\d+', m).group()) for m in source_markers]
        target_nums = [int(re.search(r'\d+', m).group()) for m in target_markers]
        
        return source_nums != target_nums
    
    def _fix_missing_markers(self, source_text: str, target_text: str, 
                            missing: set) -> Tuple[bool, str, str]:
        """
        修复缺失的标记
        策略：根据原文中标记的相对位置，在译文中对应位置插入
        """
        # 获取原文中所有标记的位置信息
        source_markers_pos = self._extract_marker_positions(source_text)
        target_markers_pos = self._extract_marker_positions(target_text)
        
        # 移除标记，得到纯文本用于对齐
        source_clean = self._remove_markers(source_text)
        target_clean = self._remove_markers(target_text)
        
        # 构建标记插入位置映射
        fixes = []
        for missing_marker in missing:
            # 找到该标记在原文中的位置
            marker_idx_in_source = None
            for marker, pos in source_markers_pos:
                if marker == missing_marker:
                    marker_idx_in_source = pos
                    break
            
            if marker_idx_in_source is None:
                continue
            
            # 计算该标记在纯文本中的位置比例
            clean_pos = self._marker_to_clean_pos(source_text, marker_idx_in_source)
            ratio = clean_pos / len(source_clean) if len(source_clean) > 0 else 0
            
            # 在译文中找到对应位置
            target_insert_pos = int(ratio * len(target_clean))
            
            # 转换回带标记文本的位置
            actual_pos = self._clean_to_marker_pos(target_text, target_insert_pos)
            
            fixes.append((missing_marker, actual_pos))
        
        # 按位置从后往前插入（避免位置偏移）
        fixed_text = target_text
        for marker, pos in sorted(fixes, key=lambda x: x[1], reverse=True):
            fixed_text = fixed_text[:pos] + marker + fixed_text[pos:]
        
        fix_msg = f"已插入缺失标记: {', '.join([m for m, _ in fixes])}"
        return True, fixed_text, fix_msg
    
    def _fix_marker_order(self, source_text: str, target_text: str) -> Tuple[bool, str, str]:
        """
        修复标记顺序错误
        策略：根据原文标记顺序，重新排列译文中的标记
        """
        # 提取纯文本和标记位置
        source_markers = self._extract_markers(source_text)
        target_markers = self._extract_markers(target_text)
        
        # 如果数量不同，无法修复顺序
        if len(source_markers) != len(target_markers):
            return False, target_text, "标记数量不一致，无法修复顺序"
        
        # 移除所有标记
        target_clean = self._remove_markers(target_text)
        
        # 使用序列匹配找到文本片段的对应关系
        source_clean = self._remove_markers(source_text)
        
        # 简化策略：假设标记按顺序对应文本片段
        # 将原文分割成标记之间的片段
        source_segments = self._split_by_markers(source_text)
        
        # 在译文中查找这些片段（使用模糊匹配）
        # 然后在片段之间插入正确的标记
        
        # TODO: 这里需要更复杂的算法，暂时返回失败
        return False, target_text, "顺序错误修复需要更复杂的算法"
    
    def _fix_complex_errors(self, source_text: str, target_text: str, 
                           missing: set) -> Tuple[bool, str, str]:
        """修复复杂错误（既有丢失又有顺序错误）"""
        # 先尝试补全缺失标记
        success, fixed_text, msg1 = self._fix_missing_markers(source_text, target_text, missing)
        
        if not success:
            return False, target_text, "复杂错误无法自动修复"
        
        # 再检查顺序
        source_markers = self._extract_markers(source_text)
        fixed_markers = self._extract_markers(fixed_text)
        
        if self._check_order(source_markers, fixed_markers):
            # 顺序仍有问题，尝试修复
            success2, final_text, msg2 = self._fix_marker_order(source_text, fixed_text)
            if success2:
                return True, final_text, msg1 + "; " + msg2
        
        return success, fixed_text, msg1
    
    def _remove_markers(self, text: str) -> str:
        """移除所有边界标记，得到纯文本"""
        return re.sub(r'<RUNBND\d+>', '', text)
    
    def _marker_to_clean_pos(self, text_with_markers: str, marker_pos: int) -> int:
        """将带标记文本中的位置转换为纯文本位置"""
        clean_pos = 0
        for i in range(marker_pos):
            if not re.match(r'<RUNBND\d+>', text_with_markers[i:i+11]):
                clean_pos += 1
        return clean_pos
    
    def _clean_to_marker_pos(self, text_with_markers: str, clean_pos: int) -> int:
        """将纯文本位置转换为带标记文本中的位置"""
        current_clean = 0
        for i, char in enumerate(text_with_markers):
            if current_clean >= clean_pos:
                return i
            # 跳过标记
            if text_with_markers[i:i+8] == '<RUNBND':
                match = re.match(r'<RUNBND\d+>', text_with_markers[i:])
                if match:
                    i += len(match.group()) - 1
                    continue
            current_clean += 1
        return len(text_with_markers)
    
    def _split_by_markers(self, text: str) -> List[str]:
        """按标记分割文本"""
        return re.split(r'<RUNBND\d+>', text)


# 使用示例
if __name__ == "__main__":
    fixer = BoundaryMarkerFixer(max_missing=3)
    
    # 测试案例1：末尾标记丢失
    source = "应进一步<RUNBND48>处理<RUNBND49>［<RUNBND50>33<RUNBND51>］<RUNBND52>。"
    target_wrong = "требует дальнейшего <RUNBND47>вмешательства<RUNBND48>［<RUNBND49>33<RUNBND50>］<RUNBND51>."
    
    success, fixed, msg = fixer.fix_markers(source, target_wrong)
    print(f"案例1 - 末尾标记丢失:")
    print(f"  成功: {success}")
    print(f"  修复后: {fixed}")
    print(f"  说明: {msg}")
    print()
    
    # 测试案例2：标记顺序错误
    source2 = "不超过<RUNBND29>1<RUNBND30>个月...耐多药<RUNBND31>/<RUNBND32>利福平"
    target_wrong2 = "мультирезистентным<RUNBND31>/<RUNBND30>...не более<RUNBND29>1<RUNBND32>месяца"
    
    success2, fixed2, msg2 = fixer.fix_markers(source2, target_wrong2)
    print(f"案例2 - 标记顺序错误:")
    print(f"  成功: {success2}")
    print(f"  修复后: {fixed2}")
    print(f"  说明: {msg2}")
