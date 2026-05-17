"""
全局配置模块
"""
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _load_project_env() -> None:
    """加载项目根目录 .env（幂等），保证任意入口都能读取环境变量。"""
    if load_dotenv is None:
        return

    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(root_env)


_load_project_env()


@dataclass
class LLMConfig:
    """LLM模型配置"""
    provider: str = "deepseek"  # openai, deepseek, anthropic, local
    # DeepSeek OpenAI 兼容：官方推荐 deepseek-v4-flash / deepseek-v4-pro（deepseek-chat 等将弃用）
    model: str = "deepseek-v4-flash"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    streaming: bool = True  # 默认启用流式输出
    # 单次 LLM / OpenAI 兼容请求超时（秒）；大文档理解、实体提取等可长达数十分钟
    request_timeout_seconds: float = 1800.0  # 30 分钟
    max_retries: int = 2


@dataclass
class ProcessingConfig:
    """文档与提取任务的并发度（线程池 worker 数）"""
    document_load_max_workers: int = 4
    file_download_max_workers: int = 4
    extraction_max_workers: int = 5


@dataclass
class DatabaseConfig:
    """数据库配置（PostgreSQL / Supabase 兼容）"""
    enabled: bool = False
    provider: str = "postgresql"  # postgresql, sqlite, etc.
    # 完整连接串：设置后优先使用（Supabase 控制台 「Database」→「Connection string」）
    url: Optional[str] = None
    host: str = "localhost"
    port: int = 5432
    database: str = "doc_intel"
    username: str = "postgres"
    password: str = ""
    # 云数据库（含 Supabase）通常需要 require；未使用 url 分段配置时生效
    sslmode: str = "prefer"
    # 连接池上限（供 db.connection 使用）
    pool_max_size: int = 10


@dataclass
class AuthConfig:
    """认证配置"""
    secret_key: str = "change-me-in-production"
    access_token_ttl_minutes: int = 60 * 24 * 7
    require_auth: bool = False


@dataclass
class FileConfig:
    """文件配置"""
    max_file_size_mb: int = 50
    supported_document_types: list = field(default_factory=lambda: ["docx", "pdf", "txt", "md"])
    supported_table_types: list = field(default_factory=lambda: ["xlsx", "xls", "csv"])


@dataclass
class StorageConfig:
    """文件存储配置（本地 / 阿里云 OSS）"""
    enabled: bool = False
    provider: str = "local"
    object_key_prefix: str = "sessions"
    oss_endpoint: Optional[str] = None
    oss_access_key_id: Optional[str] = None
    oss_access_key_secret: Optional[str] = None
    oss_bucket: Optional[str] = None


@dataclass
class AgentConfig:
    """Agent配置"""
    prompts: dict = field(default_factory=lambda: {
        "conversation": """你是一个友好的人工智能助手，基于文档智能系统运行。

系统能力：
1. 文档理解 - 解析并理解docx、pdf、txt、md等文档内容
2. 文档编辑 - 按要求编辑Word文档
3. 实体提取 - 从文档中提取数据填入Excel模板
4. 表格填表 - 从Excel筛选数据填入表格

你可以：
1. 回答用户的问题
2. 提供系统使用帮助
3. 解释系统的各项功能
4. 根据用户需求推荐合适的工作模式

请友好地与用户交流，并根据需要介绍系统的功能。""",

        "document_understanding": """【身份】你是文档智能系统的 AI 助手，运行在【文档理解模式】下。

【核心能力】
1. **文档阅读** - 支持解析 docx、pdf、txt、md、xlsx、xls 等多种格式文档
2. **内容理解** - 准确理解文档结构、文字、数据和图表
3. **智能问答** - 围绕已上传的文档内容回答用户问题，支持多轮追问
4. **统计分析** - 对表格数据进行统计（均值、中位数、标准差、分位数等）
5. **要点提炼** - 提取文档核心观点、关键信息和数据结构

【工作原则】
- 始终基于已上传的文档内容回答，不要编造未提及的信息
- 回答应简洁准确，优先使用 Markdown 格式（列表、粗体等）
- 如果用户的问题涉及文档中未包含的内容，明确告知
- 当文档包含表格数据时，先给出统计概览，再按需展开细节
- 多文档场景下，区分说明各文档的内容和回答依据

【系统说明】
- 你只能访问用户通过界面上传的文档
- 文件路径和上传信息仅供参考，请勿在回答中暴露文件物理路径""",

        "document": """你是一个专业的文档理解和编辑助手。
你有以下能力：
1. 理解并总结各类文档内容
2. 回答关于文档的问题
3. 编辑和修改Word文档
4. 进行文档格式转换

请根据用户的需求执行相应操作。""",

        "extraction": """你是一个专业的实体提取助手。
你有以下能力：
1. 理解用户的数据提取需求
2. 从非结构化文档（Word、Markdown、纯文本）中提取指定字段
3. 将提取的数据以JSON格式返回

请根据用户的需求和模板，从文档中提取相应的实体数据。""",

        "database": """你是一个数据库管理助手。
你有以下能力：
1. 根据数据结构自动创建数据库表
2. 将JSON数据存入数据库
3. 执行数据库查询操作

请根据提供的数据结构执行相应的数据库操作。""",

        "table": """你是一个表格数据处理助手。
你有以下能力：
1. 根据用户要求筛选Excel数据
2. 对数据进行统计、汇总等操作
    3. 将处理结果填入Word或Excel表格模板

    【输入约束】
    - 数据源文件应优先是 Excel（xlsx/xls/csv）
    - 模板文件可以是 Word（docx）或 Excel（xlsx）
    - 如果用户上传的是 docx 模板 + xlsx 数据文件，请明确把 docx 视为模板、xlsx 视为数据源，不要反向解释

请根据用户的需求执行相应的数据处理和填表操作。""",
    })

    def get_prompt(self, agent_type: str) -> str:
        """获取指定类型的agent提示词"""
        return self.prompts.get(agent_type, "")


@dataclass
class SystemConfig:
    """系统全局配置"""
    debug: bool = False
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    work_dir: str = "workspace"
    output_dir: str = "output"
    temp_dir: str = "temp"
    llm: LLMConfig = field(default_factory=LLMConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    file: FileConfig = field(default_factory=FileConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)


def load_config() -> SystemConfig:
    """
    加载系统配置
    支持从环境变量或配置文件加载
    """
    config = SystemConfig()

    # LLM：先读显式覆盖，再按 provider 填密钥，避免「同时写了 DEEPSEEK_API_KEY 与 LLM_PROVIDER=zhipu」导致混用密钥
    explicit_llm_model = bool(os.getenv("LLM_MODEL"))
    if os.getenv("LLM_PROVIDER"):
        config.llm.provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if os.getenv("LLM_MODEL"):
        config.llm.model = os.getenv("LLM_MODEL", "").strip()
    if os.getenv("LLM_BASE_URL"):
        config.llm.base_url = os.getenv("LLM_BASE_URL", "").strip()

    if not (config.llm.provider and str(config.llm.provider).strip()):
        if os.getenv("DEEPSEEK_API_KEY"):
            config.llm.provider = "deepseek"
        elif os.getenv("ZHIPU_API_KEY"):
            config.llm.provider = "zhipu"
        elif os.getenv("OPENAI_API_KEY"):
            config.llm.provider = "openai"

    prov = (config.llm.provider or "deepseek").strip().lower()

    if prov == "deepseek":
        if os.getenv("DEEPSEEK_API_KEY"):
            config.llm.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not explicit_llm_model:
            config.llm.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        if not config.llm.base_url:
            # 官方 OpenAI 兼容入口（勿加 /v1，LangChain/OpenAI SDK 会拼路径）
            config.llm.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    elif prov in ("zhipu", "glm"):
        if os.getenv("ZHIPU_API_KEY"):
            config.llm.api_key = os.getenv("ZHIPU_API_KEY")
        _deepseek_default_names = (
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        )
        if not explicit_llm_model and config.llm.model in _deepseek_default_names:
            config.llm.model = os.getenv("ZHIPU_MODEL", "glm-4-flash")
        if not config.llm.base_url:
            config.llm.base_url = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    elif prov in ("openai", "openai-compatible"):
        if os.getenv("OPENAI_API_KEY"):
            config.llm.api_key = os.getenv("OPENAI_API_KEY")
        if not explicit_llm_model and config.llm.model in (
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ):
            config.llm.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        if not config.llm.base_url:
            config.llm.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    # LLM 超时 / 重试（全局，适用于智谱 / DeepSeek / OpenAI）
    for env_key in ("LLM_REQUEST_TIMEOUT_SECONDS", "DEEPSEEK_REQUEST_TIMEOUT", "LLM_REQUEST_TIMEOUT"):
        val = os.getenv(env_key)
        if val:
            config.llm.request_timeout_seconds = float(val.strip())
            break
    if os.getenv("LLM_MAX_RETRIES"):
        config.llm.max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
    elif os.getenv("DEEPSEEK_MAX_RETRIES"):
        config.llm.max_retries = int(os.getenv("DEEPSEEK_MAX_RETRIES", "2"))

    if os.getenv("DOCUMENT_LOAD_MAX_WORKERS"):
        config.processing.document_load_max_workers = max(
            1, int(os.getenv("DOCUMENT_LOAD_MAX_WORKERS", "4"))
        )
    if os.getenv("FILE_DOWNLOAD_MAX_WORKERS"):
        config.processing.file_download_max_workers = max(
            1, int(os.getenv("FILE_DOWNLOAD_MAX_WORKERS", "4"))
        )
    if os.getenv("EXTRACTION_MAX_WORKERS"):
        config.processing.extraction_max_workers = max(
            1, int(os.getenv("EXTRACTION_MAX_WORKERS", "5"))
        )

    # 数据库配置（支持 DATABASE_URL / SUPABASE_DB_URL 或分段变量）
    if os.getenv("DB_ENABLED"):
        config.database.enabled = os.getenv("DB_ENABLED").lower() == "true"
    for env in ("DATABASE_URL", "SUPABASE_DB_URL", "DB_URL"):
        val = os.getenv(env)
        if val:
            config.database.url = val.strip()
            break
    if os.getenv("DB_HOST"):
        config.database.host = os.getenv("DB_HOST", "").strip()
    if os.getenv("DB_PORT"):
        config.database.port = int(os.getenv("DB_PORT", "5432"))
    if os.getenv("DB_NAME"):
        config.database.database = os.getenv("DB_NAME", "").strip()
    if os.getenv("DB_USER"):
        config.database.username = os.getenv("DB_USER", "").strip()
    if os.getenv("DB_USERNAME"):
        config.database.username = os.getenv("DB_USERNAME", "").strip()
    if os.getenv("DB_PASSWORD"):
        config.database.password = os.getenv("DB_PASSWORD", "")
    if os.getenv("DB_SSLMODE"):
        config.database.sslmode = os.getenv("DB_SSLMODE", "prefer").strip()
    if os.getenv("DB_POOL_MAX"):
        config.database.pool_max_size = int(os.getenv("DB_POOL_MAX", "10"))

    # 文件存储：仅阿里云 OSS（可选）
    if os.getenv("STORAGE_PROVIDER"):
        config.storage.provider = os.getenv("STORAGE_PROVIDER", "local").strip()
    if config.storage.provider == "oss":
        config.storage.provider = "aliyun_oss"
    if os.getenv("STORAGE_ENABLED"):
        config.storage.enabled = os.getenv("STORAGE_ENABLED").lower() == "true"
    if os.getenv("OSS_PREFIX"):
        config.storage.object_key_prefix = os.getenv("OSS_PREFIX", "sessions").strip()
    if os.getenv("OSS_ENDPOINT"):
        config.storage.oss_endpoint = os.getenv("OSS_ENDPOINT", "").strip()
    if os.getenv("OSS_ACCESS_KEY_ID"):
        config.storage.oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
    if os.getenv("OSS_ACCESS_KEY_SECRET"):
        config.storage.oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()
    if os.getenv("OSS_BUCKET"):
        config.storage.oss_bucket = os.getenv("OSS_BUCKET", "").strip()
    oss_ready = bool(
        config.storage.oss_endpoint
        and config.storage.oss_access_key_id
        and config.storage.oss_access_key_secret
        and config.storage.oss_bucket
    )
    if config.storage.provider in ("aliyun_oss", "oss") and oss_ready:
        config.storage.enabled = True
        config.storage.provider = "aliyun_oss"

    if os.getenv("AUTH_SECRET_KEY"):
        config.auth.secret_key = os.getenv("AUTH_SECRET_KEY", "change-me-in-production")
    if os.getenv("AUTH_ACCESS_TOKEN_TTL_MINUTES"):
        config.auth.access_token_ttl_minutes = int(os.getenv("AUTH_ACCESS_TOKEN_TTL_MINUTES", "10080"))
    if os.getenv("AUTH_REQUIRE_LOGIN"):
        config.auth.require_auth = os.getenv("AUTH_REQUIRE_LOGIN").lower() == "true"

    # 调试模式
    if os.getenv("DEBUG"):
        config.debug = os.getenv("DEBUG").lower() == "true"
        config.log_level = "DEBUG"

    # Agent配置
    if os.getenv("AGENT_SYSTEM_PROMPT"):
        config.agent.system_prompt = os.getenv("AGENT_SYSTEM_PROMPT")

    # 创建必要目录
    for dir_path in [config.log_file.split("/")[0] if "/" in config.log_file else config.log_file]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    Path(config.work_dir).mkdir(parents=True, exist_ok=True)
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.temp_dir).mkdir(parents=True, exist_ok=True)

    from utils.desktop_runtime import apply_desktop_config

    apply_desktop_config(config)
    return config


# 全局配置实例
_config: Optional[SystemConfig] = None


def get_config() -> SystemConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: SystemConfig):
    """设置全局配置"""
    global _config
    _config = config
    # 丢弃 LLM 单例，避免仍持有旧 base_url/model 的 ChatOpenAI 客户端
    try:
        from core.llm.llm_service import reset_llm_service

        reset_llm_service()
    except Exception:
        pass
