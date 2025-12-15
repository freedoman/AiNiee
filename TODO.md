# AiNiee 待办事项清单 (TODO List)

## 优先级说明
- 🔴 高优先级 - 影响核心功能或用户体验
- 🟡 中优先级 - 功能增强或优化
- 🟢 低优先级 - 未来计划或改进建议

---

## 1. 术语表功能优化 🔴

### 问题描述
- **排序问题**: 术语表按"频次"列排序时无法正确按数值排序（当前可能按字符串排序）
- **缺少出处信息**: 术语表中没有显示术语的来源/出处，不便于追溯和验证

### 待实现功能
- [ ] 修复频次列的数值排序功能（确保 10 > 9 > 2，而不是 9 > 2 > 10）
- [ ] 在术语表中添加"出处"列，显示术语首次出现的文件名和位置
- [ ] 支持导出时包含出处信息（JSON/Excel格式）
- [ ] 优化术语提取算法，提高准确率

### 相关文件
- `UserInterface/NameExtractor/TermResultPage.py` - 术语结果页面UI
- `ModuleFolders/SimpleExecutor/SimpleExecutor.py` - 术语提取逻辑
- `UserInterface/TableHelper/TableHelper.py` - 表格排序逻辑

### 技术方案
1. 确认 `TableHelper.py` 中的排序方法是否正确处理数值类型
2. 在术语提取时记录 `source_file` 和 `first_occurrence_line` 信息
3. 修改数据结构以存储出处信息（JSON schema 更新）
4. UI层面添加"出处"列并支持点击跳转

---

## 2. 边界标记检查与反馈机制 🔴

### 问题描述
- 当前检测到边界标记错误后，需要更精确的检查和反馈
- LLM返回错误的边界标记格式（如使用闭合标签 `</RUNBND2>`）时，应该将错误信息反馈给模型重新生成

### 待实现功能
- [x] 检测闭合标签错误（已完成）
- [x] 检测标记重复错误（已完成）
- [ ] **实现自动反馈机制**: 当检测到边界标记错误时，将详细错误信息加入到prompt中，让LLM重新翻译
- [ ] 支持多次重试（最多3次），每次都附带上一次的错误说明
- [ ] 记录边界标记错误统计，用于分析模型表现
- [ ] 优化错误提示信息，使LLM更容易理解和修正

### 相关文件
- `ModuleFolders/ResponseChecker/BaseChecks.py` - 边界标记检查逻辑
- `ModuleFolders/ResponseChecker/ResponseChecker.py` - 响应检查器
- `ModuleFolders/TaskExecutor/TaskExecutor.py` - 任务执行器（需要添加重试逻辑）

### 技术方案
```python
# 伪代码示例
max_retries = 3
for attempt in range(max_retries):
    response = llm.translate(text, prompt)
    passed, error_msg = check_boundary_markers(source, response)
    
    if passed:
        break
    else:
        # 将错误信息添加到prompt中
        feedback_prompt = f"""
        Previous translation had boundary marker errors:
        {error_msg}
        
        Please correct these errors and translate again.
        Original text: {source}
        """
        prompt = feedback_prompt
```

---

## 3. 译文字体控制 🟡

### 问题描述
- 翻译后的文本字体格式可能与原文不一致
- 需要提供灵活的字体控制选项

### 待实现功能
- [ ] **保持原文字体**: 译文继承原文的字体、大小、颜色等格式
- [ ] **统一字体设置**: 允许用户指定译文使用统一的字体样式
- [ ] **条件字体控制**: 
  - 正文使用字体A
  - 标题使用字体B
  - 引用使用字体C
- [ ] UI选项: 添加字体控制配置面板
- [ ] 支持字体映射规则（例如：宋体 → Times New Roman）

### 相关文件
- `ModuleFolders/FileAccessor/DocxAccessor.py` - DOCX文件访问器
- `ModuleFolders/FileReader/DocxReader.py` - DOCX读取器
- `ModuleFolders/FileOutputer/DocxWriter.py` - DOCX写入器

### 技术要点
1. DOCX格式中字体信息存储在 `w:rPr/w:rFonts` 中
2. 需要在读取时保存字体信息，写入时应用
3. 可能需要处理中英文字体分离（`w:ascii` vs `w:eastAsia`）
4. 考虑字体回退（fallback）机制

---

## 4. 特殊标记系统灵活化 🟡

### 问题描述
- 当前使用 `<NOTRANS>` 标记不翻译内容，但未来可能需要更多标记类型
- 缺乏统一的标记管理和扩展机制

### 待实现功能
- [ ] **设计通用标记框架**:
  ```xml
  <NOTRANS>不翻译</NOTRANS>          - 保持原文
  <KEEP_FORMAT>保留格式</KEEP_FORMAT> - 只翻译文本，保留所有格式
  <LITERAL>字面翻译</LITERAL>        - 要求逐字翻译
  <INFORMAL>口语化</INFORMAL>        - 使用口语化表达
  <FORMAL>正式</FORMAL>             - 使用正式表达
  <GLOSSARY term="xxx">术语</GLOSSARY> - 标记为术语
  ```

- [ ] **标记配置系统**:
  - JSON配置文件定义可用标记及其行为
  - UI界面动态加载标记选项
  - 支持用户自定义标记（正则规则 + 翻译策略）

- [ ] **标记自动识别**:
  - 根据文本特征自动添加标记（如检测到罗马音自动加NOTRANS）
  - 支持正则表达式规则配置
  - 提供标记预览和手动调整功能

- [ ] **标记嵌套处理**: 支持标记嵌套使用

### 相关文件
- `ModuleFolders/FileReader/DocxReader.py` - 标记添加逻辑
- `ModuleFolders/FileAccessor/DocxAccessor.py` - merge_mode的标记处理
- 新建: `ModuleFolders/MarkupManager/` - 标记管理模块

### 技术方案
```python
# 标记配置示例 (markup_config.json)
{
  "markups": [
    {
      "name": "NOTRANS",
      "type": "preserve",
      "description": "保持原文不翻译",
      "auto_detect": {
        "enabled": true,
        "rules": [
          {"regex": "\\([A-Za-z\\s]+\\)", "italic": true, "color": "FF0000"}
        ]
      }
    },
    {
      "name": "LITERAL",
      "type": "translation_style",
      "description": "字面翻译",
      "prompt_modifier": "Translate literally, word by word."
    }
  ]
}
```

---

## 5. 文本自适应模式选择 🟡

### 问题描述
- 不同类型的文本可能需要不同的翻译模式（merge_mode、边界标记等）
- 当前需要用户手动选择，缺乏智能推荐

### 待实现功能
- [ ] **文本分析引擎**:
  - 分析文本结构（段落长度、格式复杂度、标记数量）
  - 检测文本类型（小说、学术论文、技术文档、对话脚本等）
  - 统计特殊元素（表格、图片、列表、脚注等）

- [ ] **模式推荐系统**:
  ```
  场景1: 纯文本小说，段落长
    推荐: merge_mode=False, 不使用边界标记
  
  场景2: 学术论文，格式复杂，有脚注引用
    推荐: merge_mode=True, 使用边界标记, 启用位置映射
  
  场景3: 对话脚本，行短且多
    推荐: merge_mode=True, 合并多行翻译
  
  场景4: 双语对照文本
    推荐: 使用专用双语模式
  ```

- [ ] **智能模式切换**:
  - 在翻译过程中根据实际效果动态调整
  - 监控错误率，自动降级到更稳定的模式
  - 提供A/B测试功能，比较不同模式的翻译质量

- [ ] **预设配置管理**:
  - 为常见场景提供预设配置
  - 支持保存和分享自定义配置
  - 配置版本管理和导入导出

### 相关文件
- 新建: `ModuleFolders/TextAnalyzer/` - 文本分析模块
- 新建: `ModuleFolders/ModeRecommender/` - 模式推荐引擎
- `UserInterface/TranslationSettings/` - 翻译设置UI

### 技术指标
- 文本类型识别准确率 > 85%
- 模式推荐接受率 > 70%（用户采纳推荐的比例）

---

## 6. 位置映射功能优化 🔴

### 问题描述
- 当前的位置映射（use_position_mapping）功能尚不完善，不具备实际使用功能
- 边界标记与原文位置的对应关系处理不够精确

### 待实现功能
- [ ] **精确位置追踪**:
  - 记录每个run的原始位置信息（段落索引、run索引、字符偏移）
  - 建立边界标记到原文位置的精确映射表
  - 处理文本合并后的位置重计算

- [ ] **格式恢复机制**:
  - 根据位置映射精确恢复每个run的格式
  - 处理边界情况（跨run的词、标点符号等）
  - 验证格式恢复的准确性

- [ ] **错误检测与修复**:
  - 检测位置映射失败的情况
  - 提供降级策略（回退到简单的文本替换）
  - 生成位置映射质量报告

- [ ] **性能优化**:
  - 减少位置映射的内存占用
  - 优化映射查找算法（使用索引或哈希表）
  - 支持增量更新（修改部分文本时不需要重建全部映射）

### 相关文件
- `ModuleFolders/FileAccessor/DocxAccessor.py` - 核心位置映射逻辑
- `ModuleFolders/FileOutputer/DocxWriter.py` - 位置映射应用

### 技术难点
1. **边界标记与run的对应**: 一个边界标记可能对应多个run，或一个run包含多个标记
2. **翻译后的长度变化**: 译文长度与原文不同，需要调整映射
3. **格式继承规则**: 当多个run被翻译成一个词时，应该继承哪个run的格式？

### 测试用例
```
输入: 
  Run1: "Hello " (bold, red)
  Run2: "world" (italic, blue)
  边界标记: <RUNBND1>Hello <RUNBND2>world<RUNBND3>

翻译:
  "你好世界" (两个run合并成一个词)

期望输出:
  正确识别"你好"应该使用Run1的格式(bold, red)
  "世界"应该使用Run2的格式(italic, blue)
```

---

## 7. Merge_mode=False 的文本合并优化 🟡

### 问题描述
- merge_mode=False时按run逐个翻译，导致翻译割裂、上下文不连贯
- 需要在保持精确格式映射的同时，尽可能合并文本提供更多上下文

### 待实现功能
- [ ] **智能合并策略**:
  - 分析相邻run的语义关联度
  - 合并属于同一句子/短语的run
  - 保持格式边界清晰的run分离

- [ ] **上下文窗口**:
  - 为每个run提供前后N个run作为上下文（不翻译，仅供参考）
  - 在prompt中标注哪部分需要翻译，哪部分是上下文
  ```
  Context: "The quick brown"
  [TRANSLATE]: "fox"  ← 只翻译这部分
  Context: "jumps over"
  ```

- [ ] **分组翻译**:
  - 将段落分成多个组，每组包含多个run
  - 组内提供完整上下文，但每个run单独返回译文
  - 请求格式:
  ```json
  {
    "group_context": "The quick brown fox jumps",
    "runs_to_translate": [
      {"id": 1, "text": "quick", "format": {"bold": true}},
      {"id": 2, "text": "brown", "format": {"italic": true}},
      {"id": 3, "text": "fox", "format": {"color": "red"}}
    ]
  }
  ```

- [ ] **质量评估**:
  - 对比merge_mode=True/False的翻译质量
  - 提供混合模式（简单段落用False，复杂段落用True）
  - 生成质量对比报告

### 相关文件
- `ModuleFolders/FileReader/DocxReader.py` - run级别读取逻辑
- `ModuleFolders/PromptBuilder/` - prompt构建逻辑
- 新建: `ModuleFolders/ContextManager/` - 上下文管理模块

### 技术方案示例
```python
def translate_with_context(runs, context_window=2):
    """
    为每个run提供上下文后翻译
    
    Args:
        runs: 要翻译的run列表
        context_window: 前后上下文的run数量
    """
    results = []
    for i, run in enumerate(runs):
        # 获取上下文
        context_before = runs[max(0, i-context_window):i]
        context_after = runs[i+1:min(len(runs), i+context_window+1)]
        
        # 构建prompt
        prompt = f"""
        Context before: {' '.join(r.text for r in context_before)}
        [TRANSLATE THIS]: {run.text}
        Context after: {' '.join(r.text for r in context_after)}
        
        Only translate the text marked with [TRANSLATE THIS].
        """
        
        translation = llm.translate(prompt)
        results.append(translation)
    
    return results
```

---

## 8. 其他待办事项 🟢

### 8.1 性能优化
- [ ] 批量翻译时的并发控制优化
- [ ] 大文件处理的内存优化（流式处理）
- [ ] 缓存机制改进（支持部分匹配、模糊匹配）

### 8.2 用户体验
- [ ] 进度条细化（显示当前阶段：读取/翻译/写入）
- [ ] 翻译预览功能（在写入前查看译文）
- [ ] 实时翻译质量监控仪表板
- [ ] 支持翻译中途暂停和恢复

### 8.3 多语言支持
- [ ] 优化中英互译以外的语言对
- [ ] 支持多目标语言同时翻译（一次翻译生成多个语言版本）
- [ ] 区域化设置（日期格式、数字格式等）

### 8.4 质量保证
- [ ] 术语一致性检查（同一术语在全文中的翻译是否一致）
- [ ] 数字和单位检查（确保数字正确转换）
- [ ] 人名地名检查（确保专有名词翻译正确）
- [ ] 生成翻译质量报告（统计错误类型、频率等）

### 8.5 文档和测试
- [ ] 为核心模块添加单元测试
- [ ] 编写开发者文档（API文档、架构说明）
- [ ] 用户手册完善（每个功能的详细说明和最佳实践）
- [ ] 视频教程制作

---

## 优先级排序建议

### 第一阶段（当前迫切需求）
1. 🔴 **术语表排序和出处** - 影响用户日常使用
2. 🔴 **边界标记反馈机制** - 提高翻译准确率
3. 🔴 **位置映射优化** - 核心功能完善

### 第二阶段（功能增强）
4. 🟡 **特殊标记系统** - 扩展性需求
5. 🟡 **文本自适应模式** - 智能化改进
6. 🟡 **译文字体控制** - 格式控制需求

### 第三阶段（质量提升）
7. 🟡 **merge_mode=False优化** - 翻译质量改进
8. 🟢 **其他待办事项** - 长期规划

---

## 版本规划

- **v0.1.0** (当前版本): 基础功能完善
- **v0.2.0** (计划): 术语表优化 + 边界标记反馈
- **v0.3.0** (计划): 位置映射完善 + 字体控制
- **v0.4.0** (计划): 标记系统灵活化 + 智能模式选择
- **v0.5.0** (计划): 翻译质量全面优化

---

**最后更新**: 2025年12月16日  
**维护者**: AiNiee开发团队
