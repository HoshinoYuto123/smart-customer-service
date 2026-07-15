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
add_bullet('独立完成从需求到上线的 AI 项目（智能客服 Agent），全程使用 VibeCoding（Claude Code）辅助开发，了解 LangGraph + FastAPI + RAG 基础技术栈。')

# ═══════════════════════════════════════
# 核心技能
# ═══════════════════════════════════════
add_section('核心技能')
add_bullet('编程语言：掌握 C++ 基础（语法、STL、面向对象），了解 Python 基本使用。')
add_bullet('AI 应用：了解 LangChain / LangGraph 框架基础概念，理解 Agent 多节点状态机工作流程。')
add_bullet('RAG 检索增强生成：了解向量数据库（ChromaDB）基本使用、FAQ 知识库构建与混合检索（向量 + 关键词）基础流程。')
add_bullet('工具与部署：熟练使用 Office 办公软件；了解 FastAPI 基础、Git 版本控制、Docker 容器化部署；熟练使用 Claude Code 等 AI 工具进行辅助开发。')

# ═══════════════════════════════════════
# 项目经历
# ═══════════════════════════════════════
add_section('核心项目经历')

add_sub('SCS-Agent — 智能客服 Agent 系统（VibeCoding 实践）')
add_sub_info('技术栈：Python, LangGraph, FastAPI, ChromaDB, DeepSeek API  |  GitHub 开源，已部署上线')
add_bullet('使用 Claude Code 进行 VibeCoding 辅助开发，通过自然语言描述需求、拆解任务，由 AI 协助完成代码生成与调试，完成从 0 到 1 的项目构建。')
add_bullet('基于 LangChain / LangGraph 框架搭建多节点 Agent 状态机（澄清 → 路由 → 检索执行 → 回复 → 降级），实现多轮对话、反问澄清与工具调用。')
add_bullet('构建 FAQ 知识库（4 个业务域 × 40 条问答）与物流信息数据库（12 条记录），实现基础的 RAG 检索问答，支持向量语义搜索与关键词匹配。')
add_bullet('设计电商风格聊天前端界面，通过 SQLite 持久化存储实现历史会话管理与上下文记忆，支持对话恢复与 Token 感知的上下文截断。')
add_bullet('部署至 Render 平台实现公网访问，项目已开源（95+ 文件、38 个单元测试）。')

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
add_bullet('负责对接各班级团支书，询问并统计各班入党、入团情况，收集信息整理成表格，确保数据准确、按时汇总上报。')

# ═══════════════════════════════════════
# 自我评价
# ═══════════════════════════════════════
add_section('自我评价')
add_bullet('善于利用 AI 工具（Claude Code）进行 VibeCoding，能将想法快速转化为可运行的产品原型，注重实践与快速落地。')
add_bullet('有从 0 到 1 完成项目的经验，具备基本的需求拆解、代码组织与文档撰写能力，做事踏实、不浮躁。')
add_bullet('对 AI / LLM 领域有浓厚兴趣，持续关注行业动态，愿意在实际工作中深入学习与成长。')

# ── Save ──
output_path = __file__.replace('generate_resume.py', '张宇辰_求职简历_智能客服Agent.docx')
doc.save(output_path)
print(f'Done: {output_path}')
