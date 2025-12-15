

# 检查接口是否拒绝翻译，而返回一段话
def contains_special_chars(s: str) -> bool:
    special_chars = ['<', '>', '/']
    return any(char in s for char in special_chars)

# 检查数字序号是否正确
def check_dict_order(source_text_dict,input_dict):
    """
    检查输入的字典，字典的key是从零开始增加的字符数字，值是文本。
    顺序检查每个值的开头是否是以数字序号+英文句点开头，并且是从1开始增加的数字序号，
    全部检查通过返回真，反之返回假。

    Args:
        input_dict (dict): 输入的字典，key为字符数字，value为文本。

    Returns:
        bool: 检查全部通过返回True，否则返回False。
    """
    if (len(source_text_dict) == 1) and (len(input_dict) == 1):
        return True  # 一行就不检查了


    expected_num = 1  # 期望的起始序号
    keys = sorted(input_dict.keys(), key=int)  # 获取排序后的key，确保按数字顺序检查

    for key in keys:
        value = input_dict[key]
        prefix = str(expected_num) + "."
        if not value.startswith(prefix):
            return False  # 值没有以期望的序号开头
        expected_num += 1  # 序号递增

    return True  # 所有检查都通过

# 检查回复内容的文本行数
def check_text_line_count(source_dict, response_dict):
    return (
        len(source_dict) > 0 and len(response_dict) > 0 # 数据不为空
        and len(source_dict) == len(response_dict) # 原文与译文行数一致
        and all(str(key) in response_dict for key in range(len(source_dict))) # 译文的 Key 的值为从 0 开始的连续数值字符
    )

# 检查翻译内容是否有空值
def check_empty_response(response_dict):
    for value in response_dict.values():
        #检查value是不是None，因为AI回回复null，但是json.loads()会把null转化为None
        if value is None:
            return False

        # 检查value是不是空字符串，因为AI回回复空字符串，但是json.loads()会把空字符串转化为""
        if value == "":
            return False

    return True

# 检查边界标记完整性
def check_boundary_markers(source_dict, response_dict):
    """
    检查译文中的边界标记是否与原文完全一致
    
    Args:
        source_dict: 原文字典
        response_dict: 译文字典
    
    Returns:
        tuple: (是否通过, 详细错误信息)
    """
    import re
    from collections import Counter
    
    for key in source_dict.keys():
        if key not in response_dict:
            continue
            
        source_text = source_dict[key]
        response_text = response_dict[key]
        
        # 🚨 新增：检查译文中是否有错误的闭合标签(边界标记应该是自闭合的,不能有</RUNBND>)
        closing_tags = re.findall(r'</RUNBND\d+>', response_text)
        if closing_tags:
            error_msg = f"边界标记格式错误：检测到闭合标签(边界标记应该是自闭合的单标签,不能成对使用)：\n"
            error_msg += "\n".join(sorted(set(closing_tags), key=lambda x: int(re.search(r'\d+', x).group())))
            error_msg += "\n\n正确格式: <RUNBND1>内容<RUNBND2>"
            error_msg += "\n错误格式: <RUNBND1>内容</RUNBND1> (不要使用闭合标签!)"
            return False, error_msg
        
        # 提取所有边界标记(开标签)
        source_markers = re.findall(r'<RUNBND\d+>', source_text)
        response_markers = re.findall(r'<RUNBND\d+>', response_text)
        
        # 🚨 检查译文中是否有重复的标记
        response_counter = Counter(response_markers)
        duplicates = {marker: count for marker, count in response_counter.items() if count > 1}
        
        if duplicates:
            dup_list = [f"{marker}(出现{count}次)" for marker, count in sorted(duplicates.items(), key=lambda x: int(re.search(r'\d+', x[0]).group()))]
            error_msg = f"译文中存在重复的边界标记（每个标记只能出现一次）：\n" + "\n".join(dup_list)
            return False, error_msg
        
        # 检查数量
        if len(source_markers) != len(response_markers):
            missing = set(source_markers) - set(response_markers)
            extra = set(response_markers) - set(source_markers)
            
            error_msg = f"标记数量不匹配：原文{len(source_markers)}个，译文{len(response_markers)}个"
            if missing:
                error_msg += f"\n缺失: {', '.join(sorted(missing, key=lambda x: int(re.search(r'\d+', x).group())))}"
            if extra:
                error_msg += f"\n多余: {', '.join(sorted(extra, key=lambda x: int(re.search(r'\d+', x).group())))}"
            
            return False, error_msg
        
        # 检查标记顺序
        if source_markers != response_markers:
            # 找出顺序不一致的位置
            diff_positions = []
            for i, (src, rsp) in enumerate(zip(source_markers, response_markers)):
                if src != rsp:
                    diff_positions.append(f"位置{i+1}: 应为{src}实为{rsp}")
            
            if diff_positions:
                error_msg = "标记顺序错误：\n" + "\n".join(diff_positions[:5])  # 最多显示5个
                if len(diff_positions) > 5:
                    error_msg += f"\n...还有{len(diff_positions)-5}处错误"
                return False, error_msg
    
    return True, ""


# 尝试自动修复边界标记问题
def try_fix_boundary_markers(source_dict, response_dict, max_missing=3):
    """
    尝试自动修复译文中的边界标记问题
    仅当缺失标记数量较少且没有顺序错误时才修复
    
    Args:
        source_dict: 原文字典
        response_dict: 译文字典
        max_missing: 允许自动修复的最大缺失标记数
    
    Returns:
        tuple: (是否修复成功, 修复后的response_dict或原response_dict, 修复说明)
    """
    import re
    
    fixed_dict = response_dict.copy()
    fix_messages = []
    
    for key in source_dict.keys():
        if key not in response_dict:
            continue
            
        source_text = source_dict[key]
        response_text = response_dict[key]
        
        source_markers = re.findall(r'<RUNBND\d+>', source_text)
        response_markers = re.findall(r'<RUNBND\d+>', response_text)
        
        # 只处理缺失标记的情况，不处理顺序错误
        missing = set(source_markers) - set(response_markers)
        extra = set(response_markers) - set(source_markers)
        
        # 如果缺失太多或有顺序错误，不自动修复
        if len(missing) > max_missing:
            return False, response_dict, f"缺失标记过多({len(missing)}个)，不自动修复"
        
        if len(missing) == 0 and len(extra) == 0:
            continue  # 没有缺失标记
        
        # 尝试简单修复：在译文末尾添加缺失的标记
        if missing and not extra:
            fixed_text = response_text
            for marker in sorted(missing, key=lambda x: int(re.search(r'\d+', x).group())):
                # 在合适的位置插入标记（简单策略：按编号顺序插入）
                marker_num = int(re.search(r'\d+', marker).group())
                
                # 找到该标记在原文中的上下文
                marker_idx = source_text.find(marker)
                if marker_idx != -1:
                    # 提取标记前后的文本片段作为定位参考
                    before_text = source_text[max(0, marker_idx-20):marker_idx].strip()
                    after_text = source_text[marker_idx+len(marker):marker_idx+len(marker)+20].strip()
                    
                    # 在译文中查找相似位置（这里使用简单策略：按比例插入）
                    # 更复杂的实现可以使用模糊匹配
                    insert_pos = int(len(fixed_text) * (marker_idx / len(source_text)))
                    fixed_text = fixed_text[:insert_pos] + marker + fixed_text[insert_pos:]
                    
                    fix_messages.append(f"已在译文中插入{marker}")
            
            fixed_dict[key] = fixed_text
    
    if fix_messages:
        return True, fixed_dict, "；".join(fix_messages)
    
    return False, response_dict, "无法自动修复"

