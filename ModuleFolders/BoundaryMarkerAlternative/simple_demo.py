"""
位置映射系统 - 核心概念的简单演示
用最简单的代码说明工作原理
"""

class SimplePositionMapper:
    """简化版位置映射器 - 核心概念演示"""
    
    def __init__(self):
        pass
    
    def demonstrate(self):
        """演示完整流程"""
        
        print("\n" + "="*70)
        print("位置映射系统 - 核心概念演示")
        print("="*70)
        
        # ================================================================
        # 场景：翻译一个带格式的段落
        # ================================================================
        print("\n【场景】从Word中读取一个段落：")
        print('-'*70)
        
        # Word中的段落（文本 + 格式）
        original_word = {
            'text': '世界卫生组织发布报告',
            'formats': [
                {'text': '世界', 'bold': True},
                {'text': '卫生', 'italic': True},
                {'text': '组织', 'color': 'red'},
                {'text': '发布', 'bold': False},
                {'text': '报告', 'underline': True}
            ]
        }
        
        print(f"文本: {original_word['text']}")
        print("格式:")
        for fmt in original_word['formats']:
            styles = []
            if fmt.get('bold'): styles.append('加粗')
            if fmt.get('italic'): styles.append('斜体')
            if fmt.get('underline'): styles.append('下划线')
            if fmt.get('color'): styles.append(f"{fmt['color']}色")
            style_str = '+'.join(styles) if styles else '普通'
            print(f"  '{fmt['text']}' → {style_str}")
        
        # ================================================================
        # 步骤1：提取纯文本和位置信息
        # ================================================================
        print("\n【步骤1】提取纯文本和位置信息")
        print('-'*70)
        
        source_text = original_word['text']
        source_formats = []
        pos = 0
        
        for fmt in original_word['formats']:
            text_len = len(fmt['text'])
            format_info = {
                'start': pos,
                'end': pos + text_len,
                'text': fmt['text'],
                'styles': {}
            }
            # 复制样式信息
            for key in ['bold', 'italic', 'underline', 'color']:
                if key in fmt:
                    format_info['styles'][key] = fmt[key]
            
            source_formats.append(format_info)
            pos += text_len
        
        print(f"纯文本: {source_text}")
        print("位置映射表:")
        for fmt in source_formats:
            print(f"  [{fmt['start']:2d}:{fmt['end']:2d}] '{fmt['text']}' → {fmt['styles']}")
        
        # ================================================================
        # 步骤2：翻译纯文本（LLM只看到这个）
        # ================================================================
        print("\n【步骤2】LLM翻译纯文本（无格式干扰）")
        print('-'*70)
        
        # 模拟LLM翻译
        target_text = "World Health Organization published report"
        
        print(f"原文: {source_text}")
        print(f"译文: {target_text}")
        print("✅ LLM只处理纯文本，不会被标记干扰")
        
        # ================================================================
        # 步骤3：词对齐（找到对应关系）
        # ================================================================
        print("\n【步骤3】词对齐 - 找到原文和译文的对应关系")
        print('-'*70)
        
        # 简化的词对齐（实际会用算法）
        word_alignment = [
            {'source': '世界', 'target': 'World', 
             'source_pos': (0, 2), 'target_pos': (0, 5)},
            {'source': '卫生', 'target': 'Health', 
             'source_pos': (2, 4), 'target_pos': (6, 12)},
            {'source': '组织', 'target': 'Organization', 
             'source_pos': (4, 6), 'target_pos': (13, 25)},
            {'source': '发布', 'target': 'published', 
             'source_pos': (6, 8), 'target_pos': (26, 35)},
            {'source': '报告', 'target': 'report', 
             'source_pos': (8, 10), 'target_pos': (36, 42)}
        ]
        
        print("对齐结果:")
        for align in word_alignment:
            src_span = f"[{align['source_pos'][0]}:{align['source_pos'][1]}]"
            tgt_span = f"[{align['target_pos'][0]}:{align['target_pos'][1]}]"
            print(f"  '{align['source']}' {src_span} ←→ '{align['target']}' {tgt_span}")
        
        # ================================================================
        # 步骤4：格式映射（自动计算译文格式）
        # ================================================================
        print("\n【步骤4】格式映射 - 将原文格式映射到译文")
        print('-'*70)
        
        target_formats = []
        for src_fmt in source_formats:
            # 找到对应的词对齐
            for align in word_alignment:
                if (align['source_pos'][0] == src_fmt['start'] and 
                    align['source_pos'][1] == src_fmt['end']):
                    # 创建译文格式
                    target_formats.append({
                        'start': align['target_pos'][0],
                        'end': align['target_pos'][1],
                        'text': align['target'],
                        'styles': src_fmt['styles'].copy()
                    })
                    break
        
        print("译文格式表:")
        for fmt in target_formats:
            print(f"  [{fmt['start']:2d}:{fmt['end']:2d}] '{fmt['text']}' → {fmt['styles']}")
        
        # ================================================================
        # 步骤5：重建Word文档
        # ================================================================
        print("\n【步骤5】重建Word文档")
        print('-'*70)
        
        print(f"译文: {target_text}")
        print("应用格式:")
        for fmt in target_formats:
            text_segment = target_text[fmt['start']:fmt['end']]
            styles = []
            for key, value in fmt['styles'].items():
                if value and key != 'color':
                    styles.append(key)
                elif key == 'color':
                    styles.append(f"{value}-colored")
            style_str = ', '.join(styles) if styles else 'normal'
            print(f"  '{text_segment}' 设置为 {style_str}")
        
        # ================================================================
        # 对比：如果使用旧方案会怎样
        # ================================================================
        print("\n" + "="*70)
        print("【对比】如果使用旧方案（混合标记）")
        print("="*70)
        
        old_approach_text = "<RUNBND1>世界<RUNBND2>卫生<RUNBND3>组织<RUNBND4>发布<RUNBND5>报告<RUNBND6>"
        print(f"\n旧方案文本: {old_approach_text}")
        print("\n可能的翻译结果:")
        print("  ❌ World<RUNBND2> Health<RUNBND3> Organization published report<RUNBND6>")
        print("     (丢失了RUNBND1和RUNBND4、RUNBND5)")
        print()
        print("  ❌ <RUNBND1>World Health<RUNBND2> Organization<RUNBND3> published<RUNBND4> report")
        print("     (丢失了RUNBND5和RUNBND6，顺序也可能错)")
        
        print("\n新方案:")
        print(f"  ✅ {target_text}")
        print("     (永远不会丢失格式，因为格式信息独立存储！)")
        
        # ================================================================
        # 关键洞察
        # ================================================================
        print("\n" + "="*70)
        print("【关键洞察】为什么位置映射能根本性解决问题？")
        print("="*70)
        
        insights = """
1. 职责分离
   - LLM职责: 只做翻译（它擅长的事）
   - 系统职责: 管理格式映射（程序擅长的事）
   
2. 信息不丢失
   - 旧方案: 标记在文本中，可能被LLM丢失或修改
   - 新方案: 格式在独立表中，程序保证不丢失
   
3. 解耦提升质量
   - 旧方案: LLM被标记干扰，翻译质量下降
   - 新方案: LLM看到干净文本，翻译质量提升
   
4. 可维护性
   - 旧方案: Prompt工程，难以保证100%
   - 新方案: 程序逻辑，可以单元测试
   
5. 扩展性
   - 旧方案: 只能处理简单格式
   - 新方案: 可以处理任意复杂的格式信息
        """
        print(insights)
        
        # ================================================================
        # 实际代码参考
        # ================================================================
        print("\n" + "="*70)
        print("【实际代码】如何在项目中实现")
        print("="*70)
        
        code = '''
# 伪代码示意

# 1. 读取Word（提取文本和格式）
def read_word_document(docx_path):
    doc = Document(docx_path)
    for para in doc.paragraphs:
        text = para.text
        formats = []
        pos = 0
        for run in para.runs:
            formats.append({
                'start': pos,
                'end': pos + len(run.text),
                'bold': run.bold,
                'italic': run.italic,
                # ... 其他格式
            })
            pos += len(run.text)
        yield text, formats

# 2. 翻译（只给LLM纯文本）
async def translate_text(text):
    response = await llm.translate(text)
    return response

# 3. 格式映射（使用词对齐）
def map_formats(source_text, target_text, source_formats):
    # 词对齐
    alignments = align_words(source_text, target_text)
    
    # 映射格式
    target_formats = []
    for src_fmt in source_formats:
        # 找到对应的目标位置
        tgt_pos = find_target_position(src_fmt, alignments)
        target_formats.append({
            'start': tgt_pos[0],
            'end': tgt_pos[1],
            'styles': src_fmt['styles']
        })
    
    return target_formats

# 4. 写入Word（应用格式）
def write_word_document(text, formats, output_path):
    doc = Document()
    para = doc.add_paragraph()
    
    for fmt in formats:
        run = para.add_run(text[fmt['start']:fmt['end']])
        run.bold = fmt['styles'].get('bold', False)
        run.italic = fmt['styles'].get('italic', False)
        # ... 应用其他格式
    
    doc.save(output_path)
        '''
        print(code)


# ====================================================================
# 运行演示
# ====================================================================
if __name__ == "__main__":
    mapper = SimplePositionMapper()
    mapper.demonstrate()
    
    print("\n" + "="*70)
    print("演示完成！")
    print("="*70)
    print("\n总结：")
    print("  位置映射 = 格式与内容分离 + 词对齐 + 自动映射")
    print("  结果：彻底解决标记丢失和顺序错误问题")
    print("="*70)
