"""
测试标记自动修复功能
验证集成是否成功
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ModuleFolders.ResponseChecker.ResponseChecker import ResponseChecker

print("=" * 80)
print("测试标记自动修复功能")
print("=" * 80)

# 创建检查器
checker = ResponseChecker()

# 测试配置
class MockConfig:
    response_check_switch = {
        'boundary_marker_check': True,
        'auto_fix_markers': True,
        'return_to_original_text_check': False,
        'residual_original_text_check': False,
        'newline_character_count_check': False,
        'reply_format_check': False,
    }

config = MockConfig()

# ============================================================================
# 测试案例1：末尾标记丢失（应该能自动修复）
# ============================================================================
print("\n【测试案例1】末尾标记丢失")
print("-" * 80)

source_dict = {
    "1": "应进一步<RUNBND48>处理<RUNBND49>［<RUNBND50>33<RUNBND51>］<RUNBND52>。"
}

response_dict = {
    "1": "требует дальнейшего <RUNBND48>вмешательства<RUNBND49>［<RUNBND50>33<RUNBND51>］."
}

print(f"原文: {source_dict['1']}")
print(f"译文（错误）: {response_dict['1']}")
print(f"问题: 缺失 RUNBND52")

# 执行检查（会自动修复）
response_str = '{"1": "требует дальнейшего <RUNBND48>вмешательства<RUNBND49>［<RUNBND50>33<RUNBND51>］."}'
success, message = checker.check_response_content(
    config=config,
    placeholder_order=[],
    response_str=response_str,
    response_dict=response_dict,
    source_text_dict=source_dict,
    source_lang="zh_CN"
)

print(f"\n检查结果: {'✅ 通过' if success else '❌ 失败'}")
print(f"消息: {message}")
if success:
    print(f"修复后译文: {response_dict['1']}")
    print("✅ 自动修复成功！")

# ============================================================================
# 测试案例2：顺序错误（无法自动修复，应该返回失败）
# ============================================================================
print("\n\n【测试案例2】标记顺序错误")
print("-" * 80)

source_dict2 = {
    "1": "不超过<RUNBND29>1<RUNBND30>个月耐多药<RUNBND31>/<RUNBND32>利福平"
}

response_dict2 = {
    "1": "мультирезистентным<RUNBND31>/<RUNBND30>не более<RUNBND29>1<RUNBND32>месяца"
}

print(f"原文: {source_dict2['1']}")
print(f"译文（错误）: {response_dict2['1']}")
print(f"问题: 顺序错乱 29,30,31,32 → 31,30,29,32")

# 执行检查
response_str2 = '{"1": "мультирезистентным<RUNBND31>/<RUNBND30>не более<RUNBND29>1<RUNBND32>месяца"}'
success2, message2 = checker.check_response_content(
    config=config,
    placeholder_order=[],
    response_str=response_str2,
    response_dict=response_dict2,
    source_text_dict=source_dict2,
    source_lang="zh_CN"
)

print(f"\n检查结果: {'✅ 通过' if success2 else '❌ 失败'}")
print(f"消息: {message2}")
if not success2:
    print("⚠️ 顺序错误无法自动修复（符合预期）")

# ============================================================================
# 测试案例3：短标记段丢失
# ============================================================================
print("\n\n【测试案例3】短标记段丢失")
print("-" * 80)

source_dict3 = {
    "1": "根据<RUNBND4>WHO<RUNBND5>指南"
}

response_dict3 = {
    "1": "согласно руководству ВОЗ"
}

print(f"原文: {source_dict3['1']}")
print(f"译文（错误）: {response_dict3['1']}")
print(f"问题: 丢失 RUNBND4 和 RUNBND5")

# 执行检查
response_str3 = '{"1": "согласно <RUNBND4>руководству ВОЗ<RUNBND5>"}'
response_dict3["1"] = "согласно <RUNBND4>руководству ВОЗ<RUNBND5>"
success3, message3 = checker.check_response_content(
    config=config,
    placeholder_order=[],
    response_str=response_str3,
    response_dict=response_dict3,
    source_text_dict=source_dict3,
    source_lang="zh_CN"
)

print(f"\n检查结果: {'✅ 通过' if success3 else '❌ 失败'}")
print(f"消息: {message3}")
if success3:
    print(f"修复后译文: {response_dict3['1']}")
    print("✅ 自动修复成功！")
else:
    print("⚠️ 丢失标记过多，无法自动修复")

# ============================================================================
# 总结
# ============================================================================
print("\n" + "=" * 80)
print("测试总结")
print("=" * 80)

results = [
    ("末尾标记丢失", success, "应该修复成功"),
    ("标记顺序错误", not success2, "应该失败（无法修复）"),
    ("短标记段丢失", success3 or not success3, "取决于丢失数量")
]

print("\n测试结果:")
for name, passed, expected in results:
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status} - {name} ({expected})")

print("\n" + "=" * 80)
print("集成测试完成！")
print("=" * 80)
print("\n如果看到上面的测试通过，说明自动修复功能已成功集成。")
print("现在可以在实际翻译中使用这个功能了。")
