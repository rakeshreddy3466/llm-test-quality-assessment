"""Thin Anthropic Messages API wrapper that logs EVERY call to calls.jsonl.

No temperature/top_p/top_k are ever sent (these models reject them).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FORBIDDEN_PARAMS = ("temperature", "top_p", "top_k")


@dataclass
class LLMResult:
    text: str
    stop_reason: str | None
    usage: dict[str, Any]
    error: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def extract_text(response: Any) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")


def usage_dict(response: Any) -> dict[str, Any]:
    u = response.usage
    if hasattr(u, "model_dump"):
        return u.model_dump()
    return dict(u)


class LoggedLLM:
    def __init__(self, client: Any, log_path: Path, *, prompt_version: str):
        self.client = client
        self.log_path = log_path
        self.prompt_version = prompt_version
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, record: dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()

    def call(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        effort: str | None,
        meta: dict[str, Any] | None = None,
    ) -> LLMResult:
        params: dict[str, Any] = {"model": model, "max_tokens": max_tokens}
        if effort:
            params["output_config"] = {"effort": effort}
        assert not any(k in params for k in FORBIDDEN_PARAMS)
        record: dict[str, Any] = {
            "timestamp": utc_now(),
            "model": model,
            "prompt_version": self.prompt_version,
            "params": params,
            "system": system,
            "prompt": user,
            "meta": meta or {},
        }
        t0 = time.monotonic()
        try:
            response = self.client.messages.create(
                system=system, messages=[{"role": "user", "content": user}], **params
            )
        except Exception as exc:  # logged, then re-raised by caller policy
            record.update(error=f"{type(exc).__name__}: {exc}", response=None, usage=None)
            record["seconds"] = round(time.monotonic() - t0, 2)
            self._log(record)
            return LLMResult("", None, {}, error=record["error"])
        text = extract_text(response)
        usage = usage_dict(response)
        record.update(
            response=text,
            content_blocks=[
                b.model_dump() if hasattr(b, "model_dump") else str(b) for b in response.content
            ],
            stop_reason=response.stop_reason,
            usage=usage,
            request_id=getattr(response, "_request_id", None),
            seconds=round(time.monotonic() - t0, 2),
            error=None,
        )
        self._log(record)
        return LLMResult(text, response.stop_reason, usage)
