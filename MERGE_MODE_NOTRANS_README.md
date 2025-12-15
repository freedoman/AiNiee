# merge_mode=True 边界标记模式 NOTRANS 功能说明

## 功能概述

在 `merge_mode=True` 且使用边界标记的模式下,添加了对括号中红色斜体文本的 `<NOTRANS>` 标记支持,以防止 LLM 翻译这些内容(通常是音译的专有名词)。

## 修改文件

### 1. ModuleFolders/FileAccessor/DocxAccessor.py

#### 新增方法: `_is_parenthetical_italic_in_merged`

```python
def _is_parenthetical_italic_in_merged(self, t_tag: Tag, all_t_tags: list) -> bool:
    """检查 w:t 标签是否为括号中的红色斜体(merge_mode=True 专用)"""
```

**功能:**
- 检查当前 run 是否为红色斜体
- 检查前后上下文(±5个标签)是否在括号内
- 支持4种括号类型: `()` `[]` `（）` `【】`

**位置:** 第 237-296 行

#### 修改位置1: `read_paragraphs` 方法中的文本生成

**文件位置:** 第 381-388 行

**修改前:**
```python
# # 然后添加文本,如果是红色斜体则用 <NOTRANS> 包裹
# if self._is_italic_marked_run(t_tags[i]):
#     parts.append(f'<NOTRANS>{text}</NOTRANS>')
# else:
#     parts.append(text)
parts.append(text)
```

**修改后:**
```python
# 然后添加文本,如果是括号中的红色斜体则用 <NOTRANS> 包裹
if self._is_parenthetical_italic_in_merged(t_tags[i], t_tags):
    parts.append(f'<NOTRANS>{text}</NOTRANS>')
else:
    parts.append(text)
```

#### 修改位置2: `write_paragraphs` 方法中的标记移除

**文件位置:** 第 757-761 行

**修改前:**
```python
# # 预处理:移除 <NOTRANS> 标记(保留内容)
# # 这些标记已经完成使命(告诉翻译模型不翻译),写入时直接移除
# translated_text = re.sub(r'<NOTRANS>(.*?)</NOTRANS>', r'\1', translated_text)
```

**修改后:**
```python
# 预处理:移除 <NOTRANS> 标记(保留内容)
# 这些标记已经完成使命(告诉翻译模型不翻译),写入时直接移除
translated_text = re.sub(r'<NOTRANS>(.*?)</NOTRANS>', r'\1', translated_text)
```

## 工作流程

### Reader 阶段 (DocxAccessor.read_paragraphs)

1. 遍历每个段落的所有 `w:t` 标签
2. 对每个文本 run:
   - 检查是否为红色斜体(`_is_italic_marked_run`)
   - 检查是否在括号内(`_is_parenthetical_italic_in_merged`)
   - 如果两个条件都满足,添加 `<NOTRANS>` 标记
3. 生成带边界标记和 NOTRANS 标记的文本

**示例:**
```
原始文本: The Jinling school (金陵派) emerged.
Reader输出: The Jinling school<RUNBND1>(<NOTRANS>金陵派</NOTRANS>)<RUNBND2>emerged.
```

### Translation 阶段

LLM 看到 `<NOTRANS>` 标记会保持内容不翻译(根据提示词规则)

**示例:**
```
输入: The Jinling school<RUNBND1>(<NOTRANS>Jinling pai</NOTRANS>)<RUNBND2>emerged.
LLM输出: Szkoła z Jinling<RUNBND1>(<NOTRANS>Jinling pai</NOTRANS>)<RUNBND2>pojawiła się.
```

### Writer 阶段 (DocxAccessor.write_paragraphs)

1. 移除 `<NOTRANS>` 标记(保留内容)
2. 按边界标记分割文本
3. 将文本写回对应的 run

**示例:**
```
译文输入: Szkoła z Jinling<RUNBND1>(<NOTRANS>Jinling pai</NOTRANS>)<RUNBND2>pojawiła się.
移除NOTRANS: Szkoła z Jinling<RUNBND1>(Jinling pai)<RUNBND2>pojawiła się.
最终输出: Szkoła z Jinling (Jinling pai) pojawiła się.
```

## 括号检测逻辑

支持4种括号类型:
- 英文圆括号: `()`
- 英文方括号: `[]`
- 中文圆括号: `（）`
- 中文方括号: `【】`

检测范围: 当前标签前后各5个 `w:t` 标签

正则模式:
```python
pattern = f'{open_bracket}[^{close_bracket}]*?{re.escape(current_text)}[^{close_bracket}]*?{close_bracket}'
```

## 测试验证

运行测试脚本: `python test_merge_mode_notrans.py`

**测试覆盖:**
1. ✅ 括号中的斜体术语
2. ✅ 边界标记 + NOTRANS
3. ✅ 多个NOTRANS标记
4. ✅ 混合标记场景
5. ✅ 4种括号类型检测
6. ✅ NOTRANS标记移除

## 使用场景

适用于翻译包含以下内容的文档:
- 括号内的音译专有名词(如: `the Jinling school (金陵派)`)
- 括号内的技术术语罗马化形式
- 不应翻译的括号注释

## 配置要求

- `merge_mode = True` - 段落合并模式
- `extract_formats = False` - 使用边界标记(不使用格式提取)
- `mark_italic_as_red = True` - 将斜体标记为红色(默认启用)

## 注意事项

1. **仅在 merge_mode=True 且使用边界标记时生效**
2. **需要原文中斜体已被标记为红色** (通过 `mark_italic_as_red` 选项)
3. **上下文范围为±5个标签** (可根据需要调整 `context_range`)
4. **与 merge_mode=False 的 NOTRANS 功能独立** (使用不同的检测方法)

## 与 merge_mode=False 的区别

| 特性 | merge_mode=False | merge_mode=True + 边界标记 |
|------|------------------|---------------------------|
| 应用场景 | 逐 run 翻译 | 段落级翻译 |
| 检测方法 | DocxReader._is_parenthetical_italic | DocxAccessor._is_parenthetical_italic_in_merged |
| 上下文来源 | 所有 w:t 标签 | 同一段落内的 w:t 标签 |
| 标记添加位置 | DocxReader._read_individual_runs | DocxAccessor.read_paragraphs |
| 标记移除位置 | DocxWriter._write_individual_runs | DocxAccessor.write_paragraphs |

## 相关代码位置

- Reader: `ModuleFolders/FileReader/DocxReader.py` (merge_mode=False)
- Accessor (Reader): `ModuleFolders/FileAccessor/DocxAccessor.py:381-388` (merge_mode=True)
- Accessor (Writer): `ModuleFolders/FileAccessor/DocxAccessor.py:757-761` (merge_mode=True)
- Writer: `ModuleFolders/FileOutputer/DocxWriter.py` (merge_mode=False: 94-100行)
- 测试: `test_merge_mode_notrans.py`
