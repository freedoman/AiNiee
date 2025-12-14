from ModuleFolders.TaskExecutor import TranslatorUtil

from ModuleFolders.ResponseChecker.BaseChecks import (
    check_text_line_count,
    check_empty_response,
    check_dict_order,
    contains_special_chars,
    check_boundary_markers
)

from ModuleFolders.ResponseChecker.AdvancedChecks import (
    check_multiline_text, 
    check_dicts_equal, 
    detecting_remaining_original_text, 
    check_placeholders_exist,
    check_reply_format
)

from ModuleFolders.BoundaryMarkerAlternative.marker_fixer import BoundaryMarkerFixer
from ModuleFolders.BoundaryMarkerAlternative.position_mapper import PositionMapper, FormatMapping
from ModuleFolders.BoundaryMarkerAlternative.format_extractor import FormatExtractor

class ResponseChecker():
    def __init__(self):
        # 初始化标记修复器（快速修复方案）
        self.marker_fixer = BoundaryMarkerFixer(max_missing=3)
        
        # 初始化位置映射器（根本性方案）
        self.position_mapper = PositionMapper(default_method="hybrid")
        self.format_extractor = FormatExtractor()

    def check_response_content(self, config, placeholder_order, response_str, response_dict, source_text_dict, source_lang):

        source_language = TranslatorUtil.map_language_code_to_name(source_lang)
        response_check_switch = config.response_check_switch

        # 基本检查
        # 检查接口是否拒绝翻译
        if not contains_special_chars(response_str):
            error_content = f"模型已拒绝翻译或格式错误，回复内容：\n{response_str}"
            return False, error_content

        # 检查文本行数    
        if not check_text_line_count(source_text_dict, response_dict):
            return False, "【行数错误】 - 行数不一致"

        # 检查文本空行
        if not check_empty_response(response_dict):
            return False, "【行数错误】 - 行数无法对应"
        
        # 检查数字序号是否正确
        if not check_dict_order(source_text_dict, response_dict):
            return False, "【行数错误】 - 出现错行串行"

        # 检查边界标记完整性
        if response_check_switch.get('boundary_marker_check', True):
            markers_ok, marker_error = check_boundary_markers(source_text_dict, response_dict)
            if not markers_ok:
                # 尝试自动修复标记错误
                if response_check_switch.get('auto_fix_markers', True):
                    fixed_count = 0
                    fix_messages = []
                    
                    for key in source_text_dict.keys():
                        if key in response_dict:
                            success, fixed_text, fix_msg = self.marker_fixer.fix_markers(
                                source_text_dict[key], 
                                response_dict[key]
                            )
                            
                            if success:
                                response_dict[key] = fixed_text
                                fixed_count += 1
                                fix_messages.append(f"行{key}: {fix_msg}")
                    
                    # 如果有修复，重新检查
                    if fixed_count > 0:
                        markers_ok, marker_error = check_boundary_markers(source_text_dict, response_dict)
                        if markers_ok:
                            # 修复成功，记录日志但继续
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.info(f"自动修复了{fixed_count}处标记错误: {'; '.join(fix_messages[:3])}")
                        else:
                            # 修复后仍有错误
                            return False, f"【标记错误】 - 自动修复失败: {marker_error}"
                    else:
                        # 无法自动修复
                        return False, f"【标记错误】 - {marker_error}"
                else:
                    # 未启用自动修复
                    return False, f"【标记错误】 - {marker_error}"

        # 进阶检查
        # 多行文本块检查
        if response_check_switch.get('newline_character_count_check', False):
            if not check_multiline_text(source_text_dict, response_dict):
                return False, "【换行符数】 - 译文换行符数量不一致"
        
        # 返回原文检查
        if response_check_switch.get('return_to_original_text_check', False):
            if not check_dicts_equal(source_text_dict, response_dict):
                return False, "【返回原文】 - 译文与原文完全相同"
        
        # 残留原文检查
        if response_check_switch.get('residual_original_text_check', False):
            if not detecting_remaining_original_text(
                source_text_dict, 
                response_dict, 
                source_language,
            ):
                return False, "【翻译残留】 - 译文中残留部分原文"

        # 回复格式检查
        if response_check_switch.get('reply_format_check', False):
            if not check_reply_format(source_text_dict, response_dict):
                return False, "【格式错误】 - 回复格式与原文格式不匹配（单行/多行）"

        # 占位符检查
        if not check_placeholders_exist(placeholder_order, response_dict):
            return False, "【自动处理】 - 未正确保留全部的占位符"

        # 全部检查通过
        return True, "检查无误"
    
    def apply_position_mapping(self, source_text_dict: dict, response_dict: dict, 
                              format_info_dict: dict = None) -> dict:
        """
        应用位置映射到翻译结果
        将格式从原文映射到译文（不使用边界标记）
        
        Args:
            source_text_dict: 原文字典 {key: source_text}
            response_dict: 译文字典 {key: target_text}
            format_info_dict: 格式信息字典 {key: List[RunFormat]}
                            如果为None，则从带标记文本中提取
        
        Returns:
            映射结果字典 {key: FormatMapping}
        """
        mapping_results = {}
        
        for key in source_text_dict.keys():
            if key not in response_dict:
                continue
            
            source_text = source_text_dict[key]
            target_text = response_dict[key]
            
            # 移除边界标记获取纯文本
            import re
            source_clean = re.sub(r'<RUNBND\d+>', '', source_text)
            target_clean = re.sub(r'<RUNBND\d+>', '', target_text)
            
            # 获取或提取格式信息
            if format_info_dict and key in format_info_dict:
                source_runs = format_info_dict[key]
            else:
                # 从带标记文本反向推断格式（简化版）
                source_runs = self._infer_format_from_markers(source_text)
            
            # 创建映射
            mapping = FormatMapping(
                source_text=source_clean,
                target_text=target_clean,
                source_runs=source_runs
            )
            
            # 执行映射
            result = self.position_mapper.map_format(mapping)
            mapping_results[key] = result
        
        return mapping_results
    
    def _infer_format_from_markers(self, marked_text: str):
        """从带标记文本推断格式信息（简化版）"""
        import re
        from ModuleFolders.BoundaryMarkerAlternative.position_mapper import RunFormat
        
        # 提取标记位置
        markers = []
        for match in re.finditer(r'<RUNBND(\d+)>', marked_text):
            markers.append((int(match.group(1)), match.start()))
        
        # 移除标记
        clean_text = re.sub(r'<RUNBND\d+>', '', marked_text)
        
        # 假设相邻标记之间是一个格式run
        runs = []
        for i in range(0, len(markers)-1, 2):
            marker1_num, marker1_pos = markers[i]
            marker2_num, marker2_pos = markers[i+1]
            
            # 计算在纯文本中的位置
            offset1 = sum(1 for m in markers[:i] if m[1] < marker1_pos) * 10  # 粗略估计
            offset2 = sum(1 for m in markers[:i+1] if m[1] < marker2_pos) * 10
            
            start = max(0, marker1_pos - offset1)
            end = min(len(clean_text), marker2_pos - offset2)
            
            if start < end:
                runs.append(RunFormat(start=start, end=end))
        
        return runs

    def check_polish_response_content(self, config, response_str, response_dict, source_text_dict):

        response_check_switch = config.response_check_switch

        # 检查接口是否拒绝翻译
        if not contains_special_chars(response_str):
            error_content = f"模型已拒绝翻译或格式错误，回复内容：\n{response_str}"
            return False, error_content

        # 检查文本行数    
        if not check_text_line_count(source_text_dict, response_dict):
            return False, "【行数错误】 - 行数不一致"

        # 检查文本空行
        if not check_empty_response(response_dict):
            return False, "【行数错误】 - 行数无法对应"
        
        # 检查数字序号是否正确
        if not check_dict_order(source_text_dict, response_dict):
            return False, "【行数错误】 - 出现错行串行"

        # 多行文本块检查
        if response_check_switch.get('newline_character_count_check', False):
            if not check_multiline_text(source_text_dict, response_dict):
                return False, "【换行符数】 - 换行符数量不一致"

        # 全部检查通过
        return True, "检查无误"