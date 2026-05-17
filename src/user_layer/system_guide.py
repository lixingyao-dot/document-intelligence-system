"""
系统使用须知模块
提供系统功能介绍和使用指南
"""

SYSTEM_GUIDE = """
================================================================================
                          文档智能系统使用指南
================================================================================

【支持的模式】
1. 默认对话模式 - 直接与AI交流，询问系统功能，无需选择特定任务
2. 文档理解模式 - 解析并理解文档内容，回答关于文档的问题
3. 文档编辑模式 - 按要求编辑Word文档（增删改、格式转换等）
4. 实体提取模式 - 从非结构化文档中提取所需数据，填入Excel模板
5. 表格填表模式 - 从Excel筛选数据，填入Word/Excel表格模板

【支持的文件格式】
- 文档类型：docx, pdf, txt, md
- 表格类型：xlsx, xls, csv

【文件上传命令】
- upload data <文件路径>     - 上传原数据文件
- upload template <文件路径> - 上传模板文件
- files                      - 查看已上传的文件

【模式别名】
- select agent_a  - 进入文档编辑模式
- select agent_d  - 进入表格填表模式

【输出位置】
- 默认输出会保存在上传文件所在目录下，文件名会自动追加处理后缀。

【各模式文件要求】
┌────────────────────┬──────────────────┬──────────────────┐
│ 模式               │ 原数据           │ 模板             │
├────────────────────┼──────────────────┼──────────────────┤
│ 默认对话模式        │ 无需             │ 无需             │
│ 文档理解模式        │ docx/pdf/txt/md  │ 无需             │
│ 文档编辑模式        │ docx             │ 无需             │
│ 实体提取模式        │ docx/pdf/txt/md  │ xlsx             │
│ 表格填表模式        │ xlsx/xls/csv     │ xlsx/docx        │
└────────────────────┴──────────────────┴──────────────────┘

【快速开始】
1. 默认进入对话模式，可直接与AI交流
2. 使用 'menu' 查看所有工作模式
3. 使用 'select <模式>' 选择工作模式
4. 使用 'upload data <路径>' 上传原数据
5. 使用 'upload template <路径>' 上传模板
6. 输入您的需求开始处理（输出默认保存在原文件同目录）

【Agent能力说明】
- Agent_A：文档理解与编辑（支持txt, word, excel, md）
- Agent_B：实体数据提取（支持从docx, md, txt提取数据为JSON）
- Agent_C：数据存储（可选，支持PostgreSQL数据库）
- Agent_D：表格数据筛选与填表（支持xlsx填入word/excel模板）

================================================================================
"""

SYSTEM_QUESTIONS = [
    "支持", "什么", "哪些", "能做什么", "功能",
    "怎么用", "如何使用", "help", "帮助",
    "模式", "工作模式", "有哪些模式", "模式",
    "系统", "这个系统", "介绍", "说明",
]


def get_system_guide() -> str:
    """获取系统使用指南"""
    return SYSTEM_GUIDE


def is_system_question(user_input: str) -> bool:
    """
    判断用户输入是否是系统相关查询
    """
    text_lower = user_input.lower()

    # 检查是否包含系统问题的关键词
    for keyword in SYSTEM_QUESTIONS:
        if keyword in text_lower:
            return True

    # 检查是否是在询问系统功能
    if any(phrase in text_lower for phrase in [
        "你是什么", "你能做什么", "如何使用",
        "怎么使用", "有什么功能", "有哪些功能",
        "给我介绍", "介绍一下"
    ]):
        return True

    return False


def get_workflow_guide(task_type: str = None) -> str:
    """
    获取特定工作流的详细指南
    """
    guides = {
        "document_understanding": """
【文档理解模式】
使用步骤：
1. 选择或上传文档（docx/pdf/txt/md）
2. 输入您的理解需求
3. 系统将解析文档并回答您的问题

示例：
- "总结这份合同的要点"
- "这份报告的主要结论是什么？"
""",
        "document_editing": """
【文档编辑模式】
使用步骤：
1. 上传Word文档（docx）
2. 描述您的编辑需求
3. 系统将按要求修改文档

示例：
- "把第三段移到第一段"
- "把这篇文章转成markdown格式"
- "在文档开头添加摘要"
""",
        "entity_extraction": """
【实体提取模式】
使用步骤：
1. 上传非结构化文档（docx/pdf/txt/md）
2. 上传Excel模板（xlsx）
3. 描述要提取的字段
4. 系统将提取数据并填入模板

示例：
- "从这份合同中提取所有日期、甲乙双方、金额"
- "提取发票中的发票号、金额、日期"
""",
        "table_filling": """
【表格填表模式】
使用步骤：
1. 上传Excel数据源（xlsx/xls/csv）
2. 上传表格模板（xlsx/word）
3. 描述筛选条件
4. 系统将筛选数据并填入模板

示例：
- "筛选销售额大于10000的记录"
- "统计每个部门的总工资"
""",
    }

    if task_type and task_type in guides:
        return guides[task_type]

    return SYSTEM_GUIDE
