"""LLM 結構化抽取的呼叫介面（見功能規格 1.4）。

定義 ExtractionClient 這個 Protocol，讓之後要換模型（例如地端 Ollama）
只要多寫一個實作，不用動 service.py 呼叫端的程式碼。

第一個實作 AnthropicExtractionClient 用 Anthropic 的 tool use 強制輸出
結構化資料，不是單純叫模型「輸出 JSON」再自己解析——tool_choice 指定
工具名稱，模型一定會照 input_schema 的形狀輸出，格式錯誤的機率低很多。
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.booking_parser.schemas import ParsedBookingRequest

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
# 對應 app/booking_parser/prompts/extract_v1.md；改 prompt 就開新版本、
# 新檔案，不要覆蓋舊的（見該檔案開頭的說明：舊的抽取/評測紀錄都對應著
# 某個 prompt 版本，覆蓋會讓舊紀錄失去對照意義）。
PROMPT_VERSION = "v1"

_WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def _load_system_prompt(reference_datetime: datetime) -> str:
    template = (PROMPT_DIR / f"extract_{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    today_str = reference_datetime.date().isoformat()
    weekday_str = _WEEKDAY_CN[reference_datetime.weekday()]
    return template.replace("__TODAY__", today_str).replace("__WEEKDAY__", weekday_str)


class ExtractionClient(Protocol):
    name: str

    def extract(
        self,
        text: str,
        reference_datetime: datetime,
        retry_errors: list[str] | None = None,
    ) -> dict:
        """回傳 LLM 原始輸出（還沒經過 Pydantic 驗證的 dict）。retry_errors
        不是規格原文給的參數，是因為規格 1.5 要求「驗證失敗要把錯誤訊息
        附在對話中重試」，Protocol 需要這個管道才能傳達重試原因。

        呼叫端（service.py）呼叫完這個方法後，可以馬上讀
        `last_latency_ms`／`last_input_tokens`／`last_output_tokens` 這三個
        屬性取得這次呼叫的 metadata，供記錄用。"""
        ...


class AnthropicExtractionClient:
    """用 Anthropic API 的 tool use 強制輸出結構化資料。"""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        import anthropic  # 延遲 import：沒裝這個套件、也沒用到這個 client 的地方不會壞

        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise RuntimeError("尚未設定 ANTHROPIC_API_KEY 環境變數")
        self._client = anthropic.Anthropic(api_key=resolved_key)
        self.model = model or os.environ.get("LLM_MODEL", "claude-sonnet-5")
        self.last_latency_ms: int | None = None
        self.last_input_tokens: int | None = None
        self.last_output_tokens: int | None = None

    def extract(
        self,
        text: str,
        reference_datetime: datetime,
        retry_errors: list[str] | None = None,
    ) -> dict:
        system_prompt = _load_system_prompt(reference_datetime)
        user_content = text
        if retry_errors:
            user_content += (
                "\n\n【上一次輸出沒有通過驗證，請修正後重新輸出】\n"
                + "\n".join(f"- {err}" for err in retry_errors)
            )

        tool_schema = ParsedBookingRequest.model_json_schema()
        tool_schema.pop("title", None)

        start = time.monotonic()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            tools=[
                {
                    "name": "extract_booking_request",
                    "description": "把學生的約課訊息轉成結構化資料",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "extract_booking_request"},
            messages=[{"role": "user", "content": user_content}],
        )
        self.last_latency_ms = int((time.monotonic() - start) * 1000)
        self.last_input_tokens = response.usage.input_tokens
        self.last_output_tokens = response.usage.output_tokens

        tool_use_block = next(block for block in response.content if block.type == "tool_use")
        return tool_use_block.input
