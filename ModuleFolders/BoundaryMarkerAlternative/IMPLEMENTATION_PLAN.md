# 边界标记问题解决方案 - 实施计划

## 📊 当前状况

### 问题总结
1. **标记丢失**：末尾标记（如RUNBND52）容易在翻译时丢失
2. **顺序错误**：LLM调整语序时，标记顺序被打乱（如RUNBND29-32错位）
3. **Prompt无效**：再多的Prompt约束也无法100%防止LLM出错

### 根本原因
**将格式信息混入翻译文本，违反了单一职责原则**
- LLM需要同时处理"翻译"和"保持标记"两个任务
- 标记与文本内容耦合，语序调整时必然冲突

---

## ✅ 解决方案

### 阶段1：快速修复（1-3天，立即可用）

#### 实施内容
激活并集成 `marker_fixer.py` 到现有系统：

```python
# 在 ResponseChecker.py 中集成
from ModuleFolders.BoundaryMarkerAlternative.marker_fixer import BoundaryMarkerFixer

class ResponseChecker:
    def __init__(self):
        self.marker_fixer = BoundaryMarkerFixer(max_missing=3)
    
    def check_response(self, source_dict, response_dict, response_check_switch):
        # ... 现有检查逻辑 ...
        
        # 如果标记检查失败，尝试自动修复
        if response_check_switch.get('boundary_marker_check', True):
            markers_ok, marker_error = check_boundary_markers(source_dict, response_dict)
            
            if not markers_ok:
                # 尝试自动修复
                for key in source_dict.keys():
                    if key in response_dict:
                        success, fixed_text, fix_msg = self.marker_fixer.fix_markers(
                            source_dict[key], 
                            response_dict[key]
                        )
                        
                        if success:
                            response_dict[key] = fixed_text
                            logger.info(f"自动修复标记: {fix_msg}")
                            # 重新检查
                            markers_ok, _ = check_boundary_markers(source_dict, response_dict)
                
                # 如果修复后仍失败，则返回失败
                if not markers_ok:
                    return False, f"【标记错误】 - {marker_error}"
```

#### 效果预期
- ✅ **末尾标记丢失**：可以自动修复（已验证有效）
- ❌ **顺序错误**：无法自动修复（需要复杂算法）
- 📈 **成功率提升**：预计从当前的~95%提升到~98%

#### 文件清单
- [x] `marker_fixer.py` - 已创建
- [ ] 集成到 `ResponseChecker.py`
- [ ] 添加配置开关 `auto_fix_markers`（默认True）
- [ ] 更新UI，显示自动修复的次数

---

### 阶段2：根本性改进（2-4周，需要重构）

#### 实施内容
切换到**位置映射方案**（`position_mapper.py`）：

1. **修改Word读取模块** (`FileReader/`)
   ```python
   # 旧方案：插入<RUNBND>标记
   text = "<RUNBND1>世界<RUNBND2>卫生<RUNBND3>组织<RUNBND4>"
   
   # 新方案：分离文本和格式
   text = "世界卫生组织"
   format_map = FormatMapping(
       source_text=text,
       source_runs=[
           RunFormat(start=0, end=2, bold=True),
           RunFormat(start=2, end=4, italic=True),
           ...
       ]
   )
   ```

2. **修改翻译流程** (`TaskExecutor/`)
   ```python
   # LLM只翻译纯文本（无标记）
   target_text = await llm.translate(source_text)  # "Всемирная организация здравоохранения"
   
   # 格式映射
   mapper = PositionMapper()
   format_map.target_text = target_text
   format_map = mapper.map_format(format_map)
   ```

3. **修改Word写入模块** (`FileOutputer/`)
   ```python
   # 根据format_map.target_runs应用格式到Word
   for run in format_map.target_runs:
       apply_format_to_word(doc, run.start, run.end, run)
   ```

#### 技术选型
- **词对齐库**：`simalign`（轻量级，无需GPU）
  ```bash
  pip install simalign
  ```
- **备选方案**：使用位置比例映射（已实现，无需额外依赖）

#### 效果预期
- ✅ **彻底解决**：不再有标记丢失或顺序错误
- ✅ **翻译质量提升**：LLM看到的是干净的文本
- ✅ **可维护性**：格式映射可以单独调试
- 📈 **成功率**：100%（理论上）

#### 迁移策略
```python
# 支持两种模式并存
config = {
    "boundary_marker_mode": "position_mapping",  # 或 "legacy_markers"
}

if config["boundary_marker_mode"] == "position_mapping":
    # 使用新方案
    use_position_mapper()
else:
    # 使用旧方案（向后兼容）
    use_boundary_markers()
```

---

## 📅 实施时间表

### 第1周：快速修复
- [ ] Day 1-2: 集成 `marker_fixer.py` 到 ResponseChecker
- [ ] Day 3: 添加配置和UI
- [ ] Day 4: 测试验证
- [ ] Day 5: 发布更新

### 第2-4周：位置映射原型
- [ ] Week 2: 修改Word读取模块，提取格式信息
- [ ] Week 3: 实现词对齐和格式映射
- [ ] Week 4: 修改Word写入模块，应用格式

### 第5周：测试和迁移
- [ ] 对比测试两种方案
- [ ] 用户反馈收集
- [ ] 逐步切换到新方案

---

## 🔧 需要修改的文件

### 阶段1（快速修复）
1. `ModuleFolders/ResponseChecker/ResponseChecker.py` - 集成marker_fixer
2. `Resource/config.json` - 添加 `auto_fix_markers` 开关
3. `UserInterface/TranslationSettings/TranslationSettingsPage.py` - 添加UI控制

### 阶段2（位置映射）
1. `ModuleFolders/FileReader/DocxReader.py` - 读取格式信息
2. `ModuleFolders/TaskExecutor/*.py` - 修改翻译流程
3. `ModuleFolders/FileOutputer/DocxWriter.py` - 应用格式映射
4. `Base/Base.py` - 添加格式映射数据结构

---

## 🎯 成功指标

### 阶段1
- [ ] 末尾标记丢失问题修复率 > 95%
- [ ] 自动修复不引入新错误
- [ ] 处理速度无明显下降

### 阶段2
- [ ] 标记相关错误降至0
- [ ] 翻译质量评分提升 5-10%
- [ ] 用户反馈积极

---

## 💡 后续优化方向

1. **可视化编辑器**
   - 显示原文和译文的格式映射关系
   - 支持手动调整错误的映射
   - 导出/导入格式映射配置

2. **智能格式建议**
   - 基于历史数据，学习格式映射规律
   - 对于常见模式（如标题、强调等），自动优化映射

3. **多语言适配**
   - 针对不同语言对（中英、中俄等），优化词对齐算法
   - 建立语言特定的格式映射策略库

---

## 📝 测试用例

### 测试案例1：末尾标记丢失
```
原文: 应进一步<RUNBND48>处理<RUNBND49>［<RUNBND50>33<RUNBND51>］<RUNBND52>。
错误译文: требует дальнейшего <RUNBND47>вмешательства<RUNBND48>［<RUNBND49>33<RUNBND50>］<RUNBND51>.
期望: 自动插入 <RUNBND52>
```
**状态**: ✅ 阶段1可解决

### 测试案例2：顺序错误
```
原文: 不超过<RUNBND29>1<RUNBND30>个月...耐多药<RUNBND31>/<RUNBND32>利福平
错误译文: мультирезистентным<RUNBND31>/<RUNBND30>...не более<RUNBND29>1<RUNBND32>месяца
期望: 重新排序标记
```
**状态**: ⚠️ 阶段1无法解决，阶段2彻底避免

### 测试案例3：短标记段
```
原文: <RUNBND4>WHO<RUNBND5>
错误译文: ВОЗ（丢失两个标记）
期望: 自动插入缺失标记
```
**状态**: ⚠️ 阶段1部分解决，阶段2彻底避免

---

## ⚙️ 配置示例

```json
{
    "response_check_switch": {
        "boundary_marker_check": true,
        "auto_fix_markers": true  // 新增：自动修复标记
    },
    "boundary_marker_mode": "legacy_markers",  // 新增：legacy_markers | position_mapping
    "position_mapping_config": {  // 新增：位置映射配置
        "alignment_method": "ratio",  // ratio | simalign | awesome-align
        "visual_editor_enabled": false
    }
}
```

---

## 📞 联系与反馈

如有问题或建议，请：
1. 提交Issue到项目仓库
2. 参与讨论：边界标记优化方案
3. 贡献代码：欢迎PR

---

**更新时间**: 2025-12-13
**状态**: 阶段1原型已完成，等待集成
