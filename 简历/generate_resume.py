"""Generate a concise one-page Chinese resume."""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# ── Page setup (tight margins for one-page fit) ──
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = Cm(1.2)
section.bottom_margin = Cm(1.0)
section.left_margin = Cm(1.5)
section.right_margin = Cm(1.5)

# Default style
style = doc.styles['Normal']
style.font.name = '宋体'
style.font.size = Pt(10)
style.paragraph_format.space_after = Pt(0)
style.paragraph_format.space_before = Pt(0)
style.paragraph_format.line_spacing = 1.25
# Set East-Asian font
rPr = style.element.get_or_add_rPr()
rFonts = rPr.makeelement(qn('w:rFonts'), {})
rFonts.set(qn('w:eastAsia'), '宋体')
rPr.insert(0, rFonts)

# ── Helpers ──
def run_font(run, name, size, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.makeelement(qn('w:rFonts'), {})
    rFonts.set(qn('w:eastAsia'), name)
    rPr.insert(0, rFonts)
    if color:
        run.font.color.rgb = RGBColor(*color)

def add_title(text, size=20):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text)
    run_font(r, '黑体', size, True)
    return p

def add_info(text, size=9):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run(text)
    run_font(r, '宋体', size)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

def add_section(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    # bottom border
    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.makeelement(qn('w:pBdr'), {})
    b = pBdr.makeelement(qn('w:bottom'), {qn('w:val'): 'single', qn('w:sz'): '4', qn('w:space'): '1', qn('w:color'): '2E75B6'})
    pBdr.append(b); pPr.append(pBdr)
    r = p.add_run(text)
    run_font(r, '黑体', 12, True, (0x2E, 0x75, 0xB6))

def add_bullet(text, size=9.5):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.4)
    p.paragraph_format.first_line_indent = Cm(-0.25)
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run('• ' + text)
    run_font(r, '宋体', size)

def add_sub(text, size=10):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run(text)
    run_font(r, '黑体', size, True)

def add_sub_info(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run(text)
    run_font(r, '宋体', 9)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

# ═══════════════════════════════════════
# HEADER
# ═══════════════════════════════════════
add_title('张 宇 辰', 20)
add_info('电话：138-xxxx-6789  |  邮箱：zhangyuchen@example.com  |  现居：广东省深圳市')
add_info('江西财经大学 · 软件工程 · 本科（2027届）  |  GitHub：github.com/zhangyuchen')

# ═══════════════════════════════════════
# 求职意向
# ═══════════════════════════════════════
add_section('求职意向')
add_bullet('目标岗位：AI 应用开发 / 后端开发工程师（实习生）')
add_bullet('独立完成从需求到上线的全栈 AI 项目（智能客服 Agent），掌握 LangGraph + FastAPI + RAG 技术栈；代码清晰、文档完善、已部署上线。')

# ═══════════════════════════════════════
# 核心技能
# ═══════════════════════════════════════
add_section('核心技能')
add_bullet('编程语言：掌握 C++ 基础（语法、STL、面向对象），了解 Python 基本使用。')
add_bullet('AI 应用：了解 LangChain / LangGraph 框架基础概念，理解 Agent 多节点状态机工作流程。')
add_bullet('RAG 检索增强生成：了解向量数据库（ChromaDB）基本使用、FAQ 知识库构建与混合检索（向量 + 关键词）基础流程。')
add_bullet('工具与部署：了解 FastAPI 基础、Git 版本控制、Docker 容器化部署；熟练使用 Claude Code 等 AI 工具进行辅助开发。')

# ═══════════════════════════════════════
# 项目经历
# ═══════════════════════════════════════
add_section('核心项目经历')

add_sub('SCS-Agent — 智能客服 Agent 系统（全栈独立开发）')
add_sub_info('技术栈：Python, LangGraph, FastAPI, ChromaDB, DeepSeek API, SQLite, Docker  |  GitHub 开源 95+ 文件，已部署上线')
add_bullet('设计 LangGraph 五节点状态机，实现模糊输入反问澄清、关键词+RAG+LLM 三层路由、工具调用循环执行、失败自动降级的完整 Agent 链路。')
add_bullet('封装多模型 Provider 抽象层，通过 YAML 配置驱动按场景切换模型；设计装饰器式 ToolRegistry，注册 FAQ 检索、订单查询等 6 个可扩展工具。')
add_bullet('构建 4 业务域×40 条 FAQ 知识库 + 12 条真实物流数据库，实现 ChromaDB 向量 + BM25 关键词 + Cross-Encoder 重排的混合检索。')
add_bullet('实现分布式熔断器、指数退避重试、令牌桶限流；SQLite 持久化历史会话，支持对话恢复与 3000 Token 感知上下文截断；38 个单元测试全部通过。')
add_bullet('独立完成淘宝风格客服前端界面（历史会话侧边栏、快捷回复卡片、格式化消息渲染）；部署至 Render 公网可访问。')

# ═══════════════════════════════════════
# 教育背景
# ═══════════════════════════════════════
add_section('教育背景')
add_sub_info('江西财经大学  |  软件工程  |  本科（2023.09 - 2027.07）')
add_bullet('主修：软件工程、数据结构、计算机网络、操作系统、计算机组成原理（408 考纲全覆盖），具备扎实计算机基础与系统工程思维。')

# ═══════════════════════════════════════
# 校园经历
# ═══════════════════════════════════════
add_section('校园经历')
add_sub_info('校学生会组织部 · 干事（2023.09 - 2024.06）')
add_bullet('统筹全院党团关系排查，建立"通知下发-进度催收-审核归档"跟进机制，确保信息收集零遗漏；负责数据规范化整理与跨层级沟通答疑。')

# ═══════════════════════════════════════
# 自我评价
# ═══════════════════════════════════════
add_section('自我评价')
add_bullet('动手能力强、成果导向：独立完成从需求分析到部署上线的全流程，注重代码质量、错误处理与工程文档。')
add_bullet('拥抱 AI、高效协作：熟练使用 Claude Code 等 AI 工具将复杂需求拆解为可执行任务，在 AI 协作中扮演"架构师+执行者"角色。')
add_bullet('全栈视野、沟通无碍：既理解 Agent / RAG 等技术原理，也能从用户角度设计交互界面，适合做技术与业务间的桥梁。')

# ── Save ──
output_path = __file__.replace('generate_resume.py', '张宇辰_求职简历_智能客服Agent.docx')
doc.save(output_path)
print(f'Done: {output_path}')
