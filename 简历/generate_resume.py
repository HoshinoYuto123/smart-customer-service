"""Generate a professional Chinese resume based on the SCS-Agent project."""
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# ── Page setup ──
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = Cm(1.5)
section.bottom_margin = Cm(1.5)
section.left_margin = Cm(1.8)
section.right_margin = Cm(1.8)

style = doc.styles['Normal']
style.font.name = '微软雅黑'
style.font.size = Pt(10.5)
style.paragraph_format.space_after = Pt(0)
style.paragraph_format.space_before = Pt(0)
style.paragraph_format.line_spacing = 1.35

# Helper functions
def add_heading_line(text, size=20, bold=True, color=None, alignment=WD_ALIGN_PARAGRAPH.CENTER):
    p = doc.add_paragraph()
    p.alignment = alignment
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = '微软雅黑'
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p

def add_normal(text, size=10.5, bold=False, alignment=WD_ALIGN_PARAGRAPH.CENTER):
    p = doc.add_paragraph()
    p.alignment = alignment
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = '微软雅黑'
    return p

def add_section_title(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    # Add bottom border
    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.makeelement(qn('w:pBdr'), {})
    bottom = pBdr.makeelement(qn('w:bottom'), {
        qn('w:val'): 'single',
        qn('w:sz'): '4',
        qn('w:space'): '1',
        qn('w:color'): '2E75B6',
    })
    pBdr.append(bottom)
    pPr.append(pBdr)

    run = p.add_run(text)
    run.font.size = Pt(13)
    run.font.bold = True
    run.font.name = '微软雅黑'
    run.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)
    return p

def add_bullet(text, indent_level=0):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5 + indent_level * 0.5)
    p.paragraph_format.first_line_indent = Cm(-0.3)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run('• ' + text)
    run.font.size = Pt(10)
    run.font.name = '微软雅黑'
    return p

def add_project_header(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.name = '微软雅黑'
    return p

def add_role_line(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.size = Pt(10)
    run.font.name = '微软雅黑'
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    return p

# ═══════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════
add_heading_line('张 宇 辰', size=22)
add_normal('电话：138-xxxx-6789  |  邮箱：zhangyuchen@example.com  |  现居：广东省深圳市', size=9)
add_normal('江西财经大学 · 软件工程 · 本科（2027届）  |  GitHub：github.com/zhangyuchen', size=9)

# ═══════════════════════════════════════════════
# 求职意向
# ═══════════════════════════════════════════════
add_section_title('求职意向')
add_bullet('目标岗位：AI 应用开发 / 后端开发工程师（实习生）')
add_bullet('匹配优势：独立完成从需求分析到上线部署的全栈 AI 项目（智能客服 Agent），掌握 LangGraph + FastAPI + RAG 技术栈；代码结构清晰、文档完善、已部署上线；具备用 AI 工具高效构建生产级系统的能力。')

# ═══════════════════════════════════════════════
# 核心技能
# ═══════════════════════════════════════════════
add_section_title('核心技能')
add_bullet('AI Agent 开发：熟练掌握 LangGraph 多节点状态机设计（clarify → router → executor → respond → fallback），能够构建完整的 Agent 决策链路。')
add_bullet('大模型应用：深入理解 LLM Provider 抽象层设计，支持 DeepSeek / OpenAI / Claude / Qwen 多模型动态切换与按场景路由；掌握 Function Calling（工具调用）机制。')
add_bullet('RAG 检索增强生成：掌握 ChromaDB 向量存储 + BM25 关键词 + Cross-Encoder 重排的混合检索策略；熟悉知识库设计、FAQ 结构化与热更新流程。')
add_bullet('后端工程能力：FastAPI 全链路异步开发、Pydantic 数据校验、structlog 结构化日志、中间件设计；SQLite 持久化会话管理；熔断/重试/限流等弹性机制。')
add_bullet('前端与部署：独立完成电商风格客服聊天 UI（原生 HTML/CSS/JS）；Docker + K8s 容器化部署；Render 平台实际部署上线经验。')
add_bullet('AI 辅助开发（VibeCoding）：熟练使用 Claude Code / ChatGPT 进行需求拆解、代码生成、Debug 与项目迭代，能在 AI 协作下高效完成从 0 到 1 的全流程开发。')

# ═══════════════════════════════════════════════
# 核心项目经历
# ═══════════════════════════════════════════════
add_section_title('核心项目经历')

add_project_header('SCS-Agent — 智能客服 Agent 系统（全栈独立开发）')
add_role_line('项目角色：全栈开发 / 架构设计 / 部署运维  |  技术栈：Python, LangGraph, FastAPI, ChromaDB, DeepSeek API, SQLite, Docker')
add_bullet('项目概述：从零构建面向真实业务场景的生产级智能客服系统，支持多轮对话、工具调用、RAG 知识库、历史会话管理。已部署上线供公网访问。')
add_bullet('LangGraph 状态机设计：设计 clarify → router → executor → respond → fallback 五节点状态流转图，实现模糊输入反问澄清、三层路由（关键词+RAG+LLM）精准匹配业务域、工具调用循环执行、失败自动降级。')
add_bullet('LLM Provider 抽象层：封装 OpenAI / Claude / Qwen 三个 Provider，统一 chat() 与 chat_with_tools() 接口，通过 YAML 配置实现按场景（路由/澄清/回答/降级）动态切换模型。')
add_bullet('RAG 知识库系统：设计 4 个业务域×40 条 FAQ 的知识体系，实现 ChromaDB 向量语义检索 + BM25 关键词检索 + Cross-Encoder 重排的混合检索策略，支持业务域过滤与知识热更新。')
add_bullet('工具注册与调用：设计装饰器式 ToolRegistry，注册 FAQ 检索、订单查询、账户查询、工单创建、人工转接、政策检索 6 个可扩展工具；内置 12 条真实物流数据的数据库，支持按订单号/手机号/关键词多维度查询。')
add_bullet('工程化与弹性设计：实现分布式熔断器（三态状态机）、指数退避重试、令牌桶限流；YAML 模板化 Prompt 管理 + 版本控制；SQLite 持久化会话存储，支持历史对话恢复与 Token 感知的上下文截断。')
add_bullet('前端与部署：淘宝/天猫风格电商客服 UI，支持历史会话侧边栏、快捷回复卡片、格式化消息渲染；Render 平台公网上线，在线体验地址已写入项目 README。')
add_bullet('成果：GitHub 开源（95+ 文件），38 个单元测试全部通过，已实际部署上线。')

# ═══════════════════════════════════════════════
# 教育背景
# ═══════════════════════════════════════════════
add_section_title('教育背景')
add_normal('江西财经大学  |  软件工程  |  本科（2023.09 - 2027.07 ）', size=10.5, bold=False, alignment=WD_ALIGN_PARAGRAPH.LEFT)
add_bullet('主修课程：软件工程、计算机网络、数据结构、计算机组成原理、操作系统（覆盖408考纲），具备扎实计算机底层逻辑与系统工程基础。')
add_bullet('复合优势：依托财经类院校背景，在严谨工科思维外，具备一定商业敏感度与业务理解潜力。')

# ═══════════════════════════════════════════════
# 校园经历
# ═══════════════════════════════════════════════
add_section_title('校园经历')
add_normal('校学生会 · 组织部  |  干事（2023.09 - 2024.06）', size=10.5, bold=False, alignment=WD_ALIGN_PARAGRAPH.LEFT)
add_bullet('跨部门信息统筹：负责全院多个年级党团关系摸底排查，建立"通知下发-进度催收-初步审核"跟进机制，确保信息收集按时零遗漏闭环。')
add_bullet('数据整理与归档：将庞杂原始数据规范化处理，利用基础办公软件进行信息登记、分类汇总与排版，确保归档材料条理清晰、方便调阅。')
add_bullet('沟通与答疑：针对各班团支书对填报要求的疑问，提供耐心清晰的解答与指导，锻炼了跨层级沟通与问题拆解能力。')

# ═══════════════════════════════════════════════
# 自我评价
# ═══════════════════════════════════════════════
add_section_title('自我评价')
add_bullet('动手能力强，成果导向：独立完成从需求分析、架构设计、编码实现到部署上线的全流程。不仅写出能跑的代码，更注重代码质量、错误处理、日志追踪等工程细节。')
add_bullet('拥抱 AI，善于借力：通过 Claude Code 等 AI 工具大幅提升开发效率。将复杂需求拆解为 AI 可执行的具体任务，在 AI 协作中扮演"架构师+项目经理"角色。')
add_bullet('全栈视野，沟通无障碍：既理解 Agent 状态机、RAG 等技术原理，也能从用户体验角度设计交互界面。能作为技术与业务之间的"翻译桥梁"。')
add_bullet('踏实务实，持续学习：项目代码 95+ 文件、38 个测试用例、完整 README 文档，体现良好的工程习惯与职业素养。对 AI 领域保持高度热情，持续跟进前沿技术。')

# ── Save ──
output_path = __file__.replace('generate_resume.py', '张宇辰_求职简历_智能客服Agent.docx')
doc.save(output_path)
print(f'Resume saved to: {output_path}')
