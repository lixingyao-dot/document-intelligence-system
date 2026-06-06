"""小米 MiMo OpenAI 兼容接口（LangExtract 抽取）。"""
from __future__ import annotations

import os

import langextract as lx
from openai import OpenAI


@lx.providers.registry.register(r"^mimo", priority=10)
class MimoLanguageModel(lx.inference.BaseLanguageModel):
    def __init__(self, model_id: str, api_key: str | None = None, base_url: str | None = None, **kwargs):
        super().__init__()
        self.model_id = model_id
        self.api_key = api_key or os.getenv("MIMO_API_KEY") or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("MIMO_API_KEY not set")

        resolved_base = (
            base_url
            or os.getenv("MIMO_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or "https://token-plan-cn.xiaomimimo.com/v1"
        )
        self.client = OpenAI(api_key=self.api_key, base_url=resolved_base)

    def infer(self, batch_prompts, **kwargs):
        for prompt in batch_prompts:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": "你是一个结构化信息抽取系统，只输出结果，不要任何解释"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content
            yield [lx.inference.ScoredOutput(score=1.0, output=content)]
