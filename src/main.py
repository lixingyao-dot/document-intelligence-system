"""
文档智能系统 - 主程序入口

整体工作流:
1. 会话开始 用户可以上传数据源 用户可以上传模板 此时为默认对话模式
2. 用户选择任务类型

2.1 如果选择文档理解模式 需要选择一篇文档 docx/pdf/txt/md
2.2 如果选择文档编辑模式 需要选择一篇文档 docx
2.3 如果选择实体提取模式 需要选择一个非结构化文档 docx/pdf/txt/md 和一个模板 xlsx
2.4 如果选择表格填表模式 需要选择一个表格 xlsx 和一个模板 xlsx/word

3.
3.1 文档理解模式
3.1.1 选择对应解析器 解析文档
3.1.2 agent_a 该agent负责理解选择的文档内容，与用户交流

3.2 文档编辑模式
3.2.1 选择对应解析器 解析文档
3.2.2 agent_a 该agent负责按照用户要求编辑文档

3.3 实体提取模式
agent_b 负责提取实体数据为json格式 填入模板
提取成功后可选择是否存入数据库

3.4 表格填表模式
agent_d 负责按照用户要求筛选excel数据 然后填入模板

Agent能力说明:
- agent_a: 理解自然语言，文档解析(txt,word,md,excel)，文档编辑(包括增删改、格式转换等),word,txt,excel,md
- agent_b: 理解自然语言，根据用户要求和表格模版(可选)，提取非结构化数据中的所需数据为json格式，(并填入模版) word,md,txt
- agent_c: 将json数据存入数据库(可选)，可能要设计自动建表   AI建议PostgreSQL
- agent_d: 根据模版提取excel数据填入表格模版（表格模版包括word、excel）
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载.env文件
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # 尝试在src目录下查找
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config, SystemConfig
from utils.logger import setup_logger, get_logger
from user_layer.cli_interface import CLIInterface


def main():
    """主函数"""
    # 加载配置
    config = load_config()

    # 设置日志
    setup_logger(
        name="doc_intel",
        level=config.log_level,
        log_file=config.log_file if config.debug else None
    )
    logger = get_logger("main")

    logger.info("=" * 60)
    logger.info("文档智能系统启动")
    logger.info("=" * 60)

    try:
        # 创建并启动CLI界面
        cli = CLIInterface(config)
        cli.run()
    except KeyboardInterrupt:
        logger.info("用户中断，系统退出")
    except Exception as e:
        logger.error(f"系统错误: {str(e)}")
        raise
    finally:
        logger.info("系统关闭")


if __name__ == "__main__":
    main()
