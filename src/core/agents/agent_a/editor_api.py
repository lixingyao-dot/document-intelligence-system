"""AgentA 文档编辑简化调用入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.agents.base_agent import AgentResponse
from core.orchestrator.task_spec import FileInfo, FileType, TaskSpec, TaskType

from .agent_a import AgentA


def edit_document_with_agent_a(
    instruction: str,
    file_path: str,
    output_file: Optional[str] = None,
) -> AgentResponse:
    """
    使用 AgentA 执行文档编辑。

    Args:
        instruction: 自然语言编辑指令。
        file_path: 源文档路径（支持 .docx/.md/.txt/.xlsx）。
        output_file: 可选输出路径，不传则自动生成到 output 目录。

    Returns:
        AgentResponse: AgentA 执行结果。
    """
    if not instruction or not str(instruction).strip():
        raise ValueError("instruction 不能为空")

    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"文件不存在: {source}")

    ext = source.suffix.lower()
    ext_to_type = {
        ".docx": FileType.DOCX,
        ".md": FileType.MD,
        ".txt": FileType.TXT,
        ".xlsx": FileType.XLSX,
    }
    if ext not in ext_to_type:
        raise ValueError(f"当前仅支持 docx/md/txt/xlsx 编辑，收到: {ext}")

    task = TaskSpec(
        task_type=TaskType.DOCUMENT_EDITING,
        instruction=instruction.strip(),
        source_files=[
            FileInfo(
                path=str(source),
                file_type=ext_to_type[ext],
                name=source.name,
            )
        ],
        output_file=output_file,
    )

    return AgentA().execute(task)
