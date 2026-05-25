"""
首次使用（工作流列表为空）时写入的示例工作流。
均为 type=custom，与用户自建工作流相同，可编辑、保存、删除。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import SystemConfig, get_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_starter_workflows(now: Optional[str] = None) -> Dict[str, Any]:
    ts = now or _utc_now()
    return {
        "wf_starter_translation": {
            "id": "wf_starter_translation",
            "name": "文档翻译流",
            "icon": "",
            "type": "custom",
            "created_at": ts,
            "updated_at": ts,
            "nodes": [
                {
                    "id": "n_doc_input",
                    "type": "input",
                    "title": "文档输入",
                    "body": "选择源文件格式与文档来源",
                    "schemaKey": "schema-document-input",
                    "configValues": {
                        "inputFileKind": "pdf",
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    },
                },
                {
                    "id": "n_ai_translate",
                    "type": "ai",
                    "title": "AI 翻译",
                    "body": "使用大模型进行智能翻译处理",
                    "schemaKey": "schema-translate",
                    "configValues": {
                        "targetLanguage": "zh",
                        "prompt": (
                            "请将以下文档全文翻译为{target_language}，保持 Markdown/段落结构，仅输出译文。"
                            "禁止输出英语，除非目标语言就是英语。"
                        ),
                    },
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "文档输出",
                    "body": "选择输出文档库与导出格式（结果写入文档库）",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "library",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_translated",
                        "outputFormat": "pdf",
                    },
                },
            ],
            "config": {},
        },
        "wf_starter_summary": {
            "id": "wf_starter_summary",
            "name": "内容提取流",
            "icon": "",
            "type": "custom",
            "created_at": ts,
            "updated_at": ts,
            "nodes": [
                {
                    "id": "n_doc_input",
                    "type": "input",
                    "title": "文档输入",
                    "body": "选择源文件格式与文档来源",
                    "schemaKey": "schema-document-input",
                    "configValues": {
                        "inputFileKind": "pdf",
                        "inputSource": "library",
                        "spaceId": None,
                        "skipExisting": False,
                    },
                },
                {
                    "id": "n_extract",
                    "type": "ai",
                    "title": "内容提取",
                    "body": "生成摘要和提取关键要点",
                    "schemaKey": "schema-extract-summary",
                    "configValues": {
                        "extractType": "summary",
                        "summaryLength": "medium",
                        "prompt": "",
                    },
                },
                {
                    "id": "n_output",
                    "type": "output",
                    "title": "文档输出",
                    "body": "选择输出文档库与导出格式（结果写入文档库）",
                    "schemaKey": "schema-library-output",
                    "configValues": {
                        "outputMode": "library",
                        "targetSpaceId": None,
                        "namingRule": "{original_name}_summary",
                        "outputFormat": "md",
                    },
                },
            ],
            "config": {},
        },
    }


def seed_starter_workflows_if_empty(config: Optional[SystemConfig] = None) -> bool:
    """若本地尚无工作流，写入示例工作流。返回是否执行了写入。"""
    from workflow_storage import _load_all, _save_all

    cfg = config or get_config()
    if _load_all(cfg):
        return False
    _save_all(build_starter_workflows(), cfg)
    return True
