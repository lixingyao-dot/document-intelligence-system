import os

import langextract as lx
from openai import OpenAI


@lx.providers.registry.register(r"^deepseek", priority=10)
class DeepSeekLanguageModel(lx.inference.BaseLanguageModel):
    def __init__(self, model_id: str, api_key: str = None, **kwargs):
        super().__init__()
        self.model_id = model_id
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

    def infer(self, batch_prompts, **kwargs):
        for prompt in batch_prompts:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": "你是一个结构化信息抽取系统，只输出结果，不要任何解释"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )

            content = response.choices[0].message.content
            yield [lx.inference.ScoredOutput(score=1.0, output=content)]
