"""LangExtract provider registrations for extraction pipeline."""

from .deepseek_provider import DeepSeekLanguageModel
from .zhipu_provider import ZhipuLanguageModel

__all__ = ["DeepSeekLanguageModel", "ZhipuLanguageModel"]
