# 边界标记替代方案设计

## 问题分析

### 当前方案的缺陷
1. **标记与文本混合**：`<RUNBND1>文本<RUNBND2>` 让LLM难以区分标记和内容
2. **语序调整冲突**：翻译时调整语序会导致标记位置错乱
3. **末尾标记丢失**：LLM注意力机制在句尾容易忽略标记
4. **依赖Prompt约束**：无法从技术上保证标记不丢失

### 根本原因
**将格式信息编码为文本内容，违反了分离关注点的原则**

---

## 替代方案设计

### 方案A：位置映射表（推荐）✅

#### 核心思想
- 翻译时只给LLM**纯文本**（无标记）
- 格式信息存储在**独立的映射表**中
- 翻译后通过**词对齐算法**自动映射格式到译文

#### 数据结构
```python
class FormatMapping:
    """格式映射数据结构"""
    
    source_text: str  # 纯文本："世界卫生组织"
    target_text: str  # 纯文本："Всемирная организация здравоохранения"
    
    source_runs: List[RunFormat] = [
        {"start": 0, "end": 2, "style": {"bold": True}},     # "世界"
        {"start": 2, "end": 4, "style": {"italic": True}},   # "卫生"
        {"start": 4, "end": 6, "style": {"color": "red"}}    # "组织"
    ]
    
    target_runs: List[RunFormat]  # 自动计算得出
```

#### 工作流程
```
1. 提取格式 → 2. 翻译纯文本 → 3. 词对齐 → 4. 映射格式 → 5. 应用到译文
```

#### 优势
- ✅ **彻底分离**：翻译和格式完全独立
- ✅ **无标记污染**：LLM看到的是干净的文本
- ✅ **自动修复**：即使语序变化，词对齐会自动找到对应关系
- ✅ **可视化调试**：格式映射可以单独检查和修正

#### 词对齐算法
```python
def align_and_map_format(source_text, source_runs, target_text):
    """
    使用多种策略进行词对齐：
    1. 基于分词的统计对齐（fast_align）
    2. 基于语义的向量对齐（sentence-transformers）
    3. 基于规则的启发式对齐（数字、专有名词等）
    """
    
    # 1. 分词对齐
    alignment = statistical_align(source_text, target_text)
    
    # 2. 格式映射
    target_runs = []
    for run in source_runs:
        source_span = (run['start'], run['end'])
        target_span = map_span(source_span, alignment)
        target_runs.append({
            "start": target_span[0],
            "end": target_span[1],
            "style": run['style']
        })
    
    return target_runs
```

---

### 方案B：标记后置处理（次优）⚠️

#### 核心思想
- 翻译时仍使用 `<RUNBND#>` 标记
- **翻译后自动修复**标记错误
- 使用算法检测并纠正标记顺序/丢失问题

#### 修复策略
```python
def auto_fix_boundary_markers(source_text, target_text):
    """自动修复标记错误"""
    
    source_markers = extract_markers(source_text)
    target_markers = extract_markers(target_text)
    
    # 检测问题类型
    if len(target_markers) < len(source_markers):
        # 情况1：标记丢失 → 根据位置比例插入缺失标记
        return insert_missing_markers(target_text, source_markers, target_markers)
    
    elif is_order_wrong(source_markers, target_markers):
        # 情况2：顺序错误 → 根据内容相似度重新排序
        return reorder_markers(target_text, source_markers)
    
    return target_text
```

#### 优势
- ✅ **兼容现有代码**：改动最小
- ✅ **渐进式改进**：可以先修复明显错误

#### 劣势
- ❌ **治标不治本**：仍依赖启发式算法
- ❌ **复杂情况难处理**：语序大幅变化时难以修复
- ❌ **计算开销**：每次翻译都要后处理

---

### 方案C：双通道翻译（复杂）🔬

#### 核心思想
- 第一次翻译：**带标记**的文本（当前方案）
- 第二次翻译：**纯文本**（无标记）
- 对比两次结果，以纯文本为准，标记文本仅提供格式位置

#### 工作流程
```python
# 第一通道：翻译带标记文本
marked_translation = translate("<RUNBND1>世界<RUNBND2>卫生组织")
# 结果可能有错误

# 第二通道：翻译纯文本
clean_translation = translate("世界卫生组织")
# 结果更准确

# 合并：用纯文本内容 + 标记文本格式位置
final = merge_translations(marked_translation, clean_translation)
```

#### 优势
- ✅ **双重保险**：纯文本翻译质量更高
- ✅ **格式不丢失**：标记文本提供格式参考

#### 劣势
- ❌ **成本翻倍**：需要调用两次LLM
- ❌ **合并复杂**：两次翻译结果可能差异较大

---

## 推荐实施方案

### 阶段1：快速改进（1-2天）
使用**方案B（标记后置处理）**：
1. 实现 `try_fix_boundary_markers()` 函数（已有框架）
2. 添加常见错误模式的自动修复
3. 保持现有代码结构

### 阶段2：根本改进（1-2周）
迁移到**方案A（位置映射表）**：
1. 设计格式映射数据结构
2. 实现词对齐算法（可用现有库：`fast_align`, `awesome-align`）
3. 修改Word读取/写入逻辑，提取和应用格式
4. 渐进式迁移：先支持两种模式并存，再完全切换

### 阶段3：优化（长期）
- 添加格式映射的可视化界面
- 支持用户手动调整格式映射
- 建立格式映射的质量评估体系

---

## 技术实现参考

### 词对齐库推荐
```bash
# 统计对齐
pip install fast-align

# 神经对齐
pip install awesome-align

# 轻量级对齐
pip install simalign
```

### 示例代码
```python
from simalign import SentenceAligner

# 初始化对齐器
aligner = SentenceAligner(model="bert", token_type="bpe", matching_methods="mai")

# 对齐
source = "世界卫生组织"
target = "World Health Organization"
alignments = aligner.get_word_aligns(source, target)

# 结果：[(0,0), (1,1), (2,2)] 表示字符级对齐
```

---

## 成本收益分析

| 方案 | 实施成本 | 翻译质量 | 维护成本 | 推荐度 |
|------|---------|---------|---------|--------|
| 当前方案 + Prompt优化 | 低 | ⭐⭐ | 高（持续调整Prompt） | ❌ |
| 方案B：标记后置处理 | 中 | ⭐⭐⭐ | 中 | ⚠️ 过渡方案 |
| 方案A：位置映射表 | 高 | ⭐⭐⭐⭐⭐ | 低 | ✅ 最终方案 |
| 方案C：双通道翻译 | 高 | ⭐⭐⭐⭐ | 中（LLM成本翻倍） | ❌ |

---

## 结论

**立即行动建议**：
1. 先实现方案B的自动修复功能（激活 `try_fix_boundary_markers()`）
2. 并行开发方案A的原型，在测试环境验证
3. 2-4周后切换到方案A作为默认方案

**长期目标**：
- 彻底放弃在翻译文本中插入标记的方式
- 采用独立的格式映射系统
- 让LLM只专注于翻译任务
