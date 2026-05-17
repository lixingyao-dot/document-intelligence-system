"""Action-file compatibility matrix and pre-execution validator for AgentA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.orchestrator.task_spec import FileInfo

from .action_plan import ActionPlan


# 动作-文件类型兼容矩阵（硬约束）
ACTION_FILE_COMPATIBILITY: Dict[str, Dict[str, Dict[str, str]]] = {
    "bold_heading": {
        "docx": {
            "status": "supported",
            "hint": "docx 将通过段落/Run 样式应用标题加粗。",
        },
        "md": {
            "status": "supported",
            "hint": "md 将转换为 markdown 标题粗体语法。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "改用“批量格式化”以设置单元格字体加粗。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "改用“内容提取”或“段落重排”；txt 不支持标题样式。",
        },
    },
    "insert_page_number": {
        "docx": {
            "status": "supported",
            "hint": "docx 将在页脚插入页码域。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "先转换为 docx 再插入页码。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持文档页码，建议改为添加页签/打印设置。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持页码，建议转为 docx 后再处理。",
        },
    },
    "unify_style": {
        "docx": {
            "status": "supported",
            "hint": "docx 将统一字体、段落间距、对齐等样式。",
        },
        "md": {
            "status": "supported",
            "hint": "md 将统一标题层级、列表与空行风格。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 将统一单元格字体、对齐与边框样式。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 将做文本级规范化（缩进、空行、分段样式）。",
        },
    },
    "reorder_paragraphs": {
        "docx": {
            "status": "supported",
            "hint": "docx 将按段落索引进行重排。",
        },
        "md": {
            "status": "supported",
            "hint": "md 将按段落块进行重排。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 将执行简单行重排（行排序/区域重排）。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 将按段落分块进行重排。",
        },
    },
    "batch_format": {
        "docx": {
            "status": "supported",
            "hint": "docx 将批量应用字体、段落、对齐等格式。",
        },
        "md": {
            "status": "supported",
            "hint": "md 将批量规范标题、列表、引用等标记格式。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 将转换为单元格样式批量处理（字体/边框/对齐）。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持样式格式化，建议改为内容规范化或转为 docx。",
        },
    },
    "extract_content": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持结构化内容提取。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持内容提取与字段抽取。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 支持表格字段提取。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 支持文本字段抽取。",
        },
    },
    "replace_text": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持查找替换文本。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持按文本匹配进行替换。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 支持单元格文本替换。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 支持全文文本替换。",
        },
    },
    "insert_toc": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持插入目录（TOC）。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持生成目录列表（基于标题层级）。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持文档目录，建议改为冻结表头或创建目录工作表。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 无结构目录，建议转换为 md/docx 后插入目录。",
        },
    },
    "auto_column_width": {
        "docx": {
            "status": "unsupported",
            "suggestion": "docx 无列宽概念，建议改为批量格式化。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 无列宽控制，建议改为表格对齐规范化。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 支持自动列宽。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持列宽，建议转为 xlsx 后处理。",
        },
    },
    "freeze_header_row": {
        "docx": {
            "status": "unsupported",
            "suggestion": "docx 不支持冻结表头，建议使用表格标题重复行。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持冻结表头，建议转为 xlsx 后处理。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 支持冻结首行/表头。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持冻结表头，建议转为 xlsx 后处理。",
        },
    },
    "clear_document_content": {
        "docx": {
            "status": "supported",
            "hint": "docx 将清空正文段落与表格单元格文字。",
        },
        "md": {
            "status": "supported",
            "hint": "md 将清空全部文本内容。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 请改用批量清空单元格或数据处理动作。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 将清空全部文本。",
        },
    },
    "remove_blank_lines": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持清理空段落/空行。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持清理多余空行并规范段落间距。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议改用删除空白行（表格行）动作。",
        },
        "txt": {
            "status": "supported",
            "hint": "txt 支持删除空行与空白字符规范化。",
        },
    },
    "set_font_family": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置字体族（如宋体/黑体/Times New Roman）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持字体族，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格样式动作设置字体。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持字体样式，建议转为 docx 后处理。",
        },
    },
    "set_font_color": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置字体颜色（hex 或中文颜色名）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持字体颜色，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格样式动作设置字体颜色。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持字体颜色，建议转为 docx 后处理。",
        },
    },
    "set_font_size": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置字号（磅值）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持字号，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格样式动作设置字号。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持字号，建议转为 docx 后处理。",
        },
    },
    "set_paragraph_alignment": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持左对齐/居中/右对齐/两端对齐。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 段落对齐能力有限，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格对齐动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持段落对齐样式。",
        },
    },
    "set_line_spacing": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置行距（如 1.0/1.5/2.0）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持行距样式，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议改为行高设置动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持行距样式。",
        },
    },
    "set_first_line_indent": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置段落首行缩进（如 2 字符）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持首行缩进样式，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持段落首行缩进，建议改为单元格对齐/缩进。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持首行缩进样式。",
        },
    },
    "set_highlight": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持为文本添加黄色高亮标记。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 原生不支持高亮，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "supported",
            "hint": "xlsx 支持为单元格文本添加背景色高亮。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持文本高亮样式。",
        },
    },
    "insert_table": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持在指定位置插入表格，支持表头加粗。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持转换为 markdown 表格格式。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 本身就是表格结构，建议改用 batch_format 或直接操作工作表。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持表格结构，建议先转为 docx 或 xlsx。",
        },
    },
    "insert_footer_text": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持在页脚插入自定义文本，支持对齐方式和页码。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持页脚，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持页脚文本，建议改为页眉/页脚打印设置。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持页脚功能。",
        },
    },
    "set_heading_numbering": {
        "docx": {
            "status": "supported",
            "hint": 'docx 支持为标题添加自动编号(如"第1章")。',
        },
        "md": {
            "status": "supported",
            "hint": "md 支持为标题添加内容前缀。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持标题编号，建议改为在单元格中手动添加。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持标题样式。",
        },
    },
    "set_italic": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持对文本应用斜体格式。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持斜体格式 (*text* 或 _text_)。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格样式动作应用斜体。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持文本格式。",
        },
    },
    "set_underline": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持对文本应用下划线格式。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 标准格式不支持下划线，可转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格样式动作应用下划线。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持文本格式。",
        },
    },
    "set_paragraph_spacing": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持设置段前距离和段后距离（磅值）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 段落间距能力有限，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 使用行高调整，建议改用相应的单元格格式动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持段落间距设置。",
        },
    },
    "set_bullet_list": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持将段落转换为项目符号列表。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持使用 - 或 * 创建项目符号列表。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持项目符号列表，建议改用单元格格式。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持列表格式。",
        },
    },
    "set_numbered_list": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持将段落转换为编号列表。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持使用 1. 2. 等创建编号列表。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 不支持编号列表，建议结合列单元格内容使用。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持列表格式。",
        },
    },
    "set_paragraph_shading": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持为段落设置背景底纹色（任意 RGB 颜色）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持段落底纹，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格背景颜色动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持底纹功能。",
        },
    },
    "set_paragraph_border": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持为段落添加边框（上下左右）。",
        },
        "md": {
            "status": "unsupported",
            "suggestion": "md 不支持段落边框，建议转为 docx 后处理。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 建议使用单元格边框动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持边框功能。",
        },
    },
    "add_hyperlink": {
        "docx": {
            "status": "supported",
            "hint": "docx 支持添加超链接（URL 或内部书签）。",
        },
        "md": {
            "status": "supported",
            "hint": "md 支持超链接格式 [text](url)。",
        },
        "xlsx": {
            "status": "unsupported",
            "suggestion": "xlsx 可使用公式 HYPERLINK() 创建超链接，建议改用相应动作。",
        },
        "txt": {
            "status": "unsupported",
            "suggestion": "txt 不支持超链接。",
        },
    },
}


@dataclass
class PrecheckResult:
    """Pre-execution compatibility check result."""

    is_valid: bool
    errors: List[Dict[str, Any]]
    hints: List[Dict[str, Any]]


def validate_action_plan_against_files(action_plan: ActionPlan, files: List[FileInfo]) -> PrecheckResult:
    """Validate action compatibility against source file types before execution."""
    errors: List[Dict[str, Any]] = []
    hints: List[Dict[str, Any]] = []

    for action in action_plan.actions:
        action_type = action.action_type.value
        action_matrix = ACTION_FILE_COMPATIBILITY.get(action_type, {})

        for file_info in files:
            file_type = file_info.file_type.value.lower()
            rule = action_matrix.get(file_type)

            if not rule:
                errors.append(
                    {
                        "action_type": action_type,
                        "file_type": file_type,
                        "reason": f"未定义该动作与 {file_type} 的兼容规则",
                        "suggestion": "请改用 extract_content 或检查能力矩阵配置。",
                    }
                )
                continue

            if rule.get("status") != "supported":
                errors.append(
                    {
                        "action_type": action_type,
                        "file_type": file_type,
                        "reason": f"{action_type} 不支持 {file_type}",
                        "suggestion": rule.get("suggestion", "请更换兼容动作。"),
                    }
                )
            else:
                hints.append(
                    {
                        "action_type": action_type,
                        "file_type": file_type,
                        "hint": rule.get("hint", ""),
                    }
                )

    return PrecheckResult(is_valid=len(errors) == 0, errors=errors, hints=hints)
