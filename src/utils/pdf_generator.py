"""
Markdown / Plain Text → PDF 生成器（基于 reportlab）。
支持中文、多级标题、代码块、表格。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 字体路径（Windows 常用中文字体，优先使用系统自带）
FONT_DIR = Path("C:/WINDOWS/Fonts")
CHINESE_FONT_CANDIDATES = [
    ("msyh.ttc", "Microsoft YaHei"),
    ("msyhbd.ttc", "Microsoft YaHei Bold"),
    ("simhei.ttf", "SimHei"),
    ("simsun.ttc", "SimSun"),
    ("NotoSansSC-VF.ttf", "NotoSansSC"),
]

# 全局注册字体别名（模块级别只注册一次）
_font_normal: str = "Helvetica"
_font_bold: str = "Helvetica-Bold"
_font_registered: bool = False


def _register_chinese_font() -> None:
    """注册中文字体到 reportlab，全局只执行一次。"""
    global _font_normal, _font_bold, _font_registered
    if _font_registered:
        return
    _font_registered = True

    for font_file, font_label in CHINESE_FONT_CANDIDATES:
        p = FONT_DIR / font_file
        if not p.exists():
            continue
        try:
            # 用唯一别名注册，避免与内置字体同名冲突
            alias = "ChineseFont"
            pdfmetrics.registerFont(TTFont(alias, str(p)))
            _font_normal = alias
            _font_bold = alias  # 同一体（reportlab 不支持粗体别名）
            return
        except Exception:
            continue

    # 全部失败：用内置 Helvetica
    _font_normal = "Helvetica"
    _font_bold = "Helvetica-Bold"


def _get_fonts() -> tuple:
    _register_chinese_font()
    return _font_normal, _font_bold


def text_to_pdf(
    text: str,
    output_path: str | Path,
    title: str = "",
    font_size: int = 11,
    line_spacing: float = 1.5,
) -> Path:
    """
    将 markdown 或纯文本内容渲染为 PDF 文件。

    - markdown 标题 (# ## ###) → 加大加粗
    - 代码块 (``` ```) → 等宽灰色背景
    - 表格 (| ... |) → 表格样式
    - 空行 → Spacer
    - 其余 → 正文
    """
    path = Path(output_path)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title or path.stem,
    )

    fn_normal, fn_bold = _get_fonts()

    def sty(name: str, **kwargs) -> ParagraphStyle:
        return ParagraphStyle(name, **kwargs)

    def sty_copy(base: ParagraphStyle, **kwargs) -> ParagraphStyle:
        """基于已有样式复制，只取 style 相关的属性。"""
        base_dict = {k: v for k, v in base.__dict__.items()
                     if k not in ('_name', 'parent', 'name')}
        base_dict.update(kwargs)
        return ParagraphStyle("_copied", **base_dict)

    s_title = sty("MyTitle", fontName=fn_bold, fontSize=22, leading=28,
                  alignment=TA_CENTER, spaceAfter=12, textColor=colors.HexColor("#1a1a2e"))
    s_h1 = sty("MyH1", fontName=fn_bold, fontSize=18, leading=24,
               spaceBefore=18, spaceAfter=8, textColor=colors.HexColor("#16213e"))
    s_h2 = sty("MyH2", fontName=fn_bold, fontSize=15, leading=20,
               spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0f3460"))
    s_h3 = sty("MyH3", fontName=fn_bold, fontSize=13, leading=18,
               spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1a1a2e"))
    s_body = sty("MyBody", fontName=fn_normal, fontSize=font_size,
                 leading=font_size * line_spacing, spaceAfter=4,
                 textColor=colors.HexColor("#333333"))
    s_code = sty("MyCode", fontName="Courier", fontSize=9, leading=13,
                 spaceBefore=4, spaceAfter=4, leftIndent=16,
                 textColor=colors.HexColor("#2d2d2d"))
    s_th = sty("MyTh", fontName=fn_bold, fontSize=font_size - 1, leading=14,
               alignment=TA_CENTER, textColor=colors.white)
    s_td = sty("MyTd", fontName=fn_normal, fontSize=font_size - 1, leading=14,
               textColor=colors.HexColor("#333333"))
    s_quote = sty("MyQuote", fontName=fn_normal, fontSize=font_size,
                  leading=font_size * line_spacing, leftIndent=20, rightIndent=20,
                  spaceAfter=4, textColor=colors.HexColor("#555555"))

    story: List = []

    if title:
        story.append(Paragraph(title, s_title))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 12))

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 标题
        if stripped.startswith("### "):
            story.append(Paragraph(_esc(stripped[4:]), s_h3))
        elif stripped.startswith("## "):
            story.append(Paragraph(_esc(stripped[3:]), s_h2))
        elif stripped.startswith("# "):
            story.append(Paragraph(_esc(stripped[2:]), s_h1))
        # 代码块
        elif stripped.startswith("```"):
            code_lines: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(_esc(lines[i]))
                i += 1
            story.append(Paragraph("<br/>".join(code_lines), s_code))
            story.append(Spacer(1, 6))
        # 表格
        elif stripped.startswith("|") and stripped.endswith("|"):
            rows, i = _parse_table(lines, i)
            if rows:
                ncols = len(rows[0])
                col_w = (A4[0] - 4 * cm) / ncols
                tbl_data = []
                for ri, row in enumerate(rows):
                    p_row = [
                        Paragraph(_render(row[ci], s_th if ri == 0 else s_td),
                                  s_th if ri == 0 else s_td)
                        for ci in range(ncols)
                    ]
                    tbl_data.append(p_row)
                tbl = Table(tbl_data, colWidths=[col_w] * ncols, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3460")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), fn_bold),
                    ("FONTSIZE", (0, 0), (-1, -1), font_size - 1),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f9f9f9")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 10))
        # 引用
        elif stripped.startswith("> "):
            story.append(Paragraph(_render(stripped[2:], s_body), s_quote))
        # 列表
        elif re.match(r"^(\s*)[-*+]\s+", stripped) or re.match(r"^(\s*)\d+\.\s+", stripped):
            m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)", stripped)
            if m:
                indent, bullet, rest = m.groups()
                lvl = len(indent) // 2
                story.append(Paragraph(_render(f"{'  ' * lvl}{bullet} {rest}", s_body),
                                       sty_copy(s_body, leftIndent=16 + lvl * 16)))
        # 空行
        elif not stripped:
            story.append(Spacer(1, 6))
        # 正文
        else:
            story.append(Paragraph(_render(stripped, s_body), s_body))

        i += 1

    doc.build(story)
    return path


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render(text: str, base_style: ParagraphStyle) -> str:
    """将 markdown 行内样式转为 reportlab XML 标记。"""
    result = _esc(text)
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result)
    result = re.sub(r"\*(.+?)\*", r"<i>\1</i>", result)
    result = re.sub(r"_(.+?)_", r"<i>\1</i>", result)
    result = re.sub(r"`(.+?)`", r"<font face='Courier' color='#c7254e'>\1</font>", result)
    return result


def _parse_table(lines: List[str], start: int) -> tuple:
    """解析 markdown 表格，返回 (rows, next_idx)。"""
    rows: List[List[str]] = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|") or not line.endswith("|"):
            break
        row = [c.strip() for c in line.strip("|").split("|")]
        # 跳过对齐行
        if all(re.match(r"^[\s:|-]+$", c) for c in row):
            i += 1
            continue
        rows.append(row)
        i += 1
        if len(rows) > 30:
            break
    return rows, i

