from __future__ import annotations

import asyncio
import json
import os
from threading import Lock
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InferenceError(RuntimeError):
    pass


class InferenceClient(Protocol):
    async def specialist(self, role: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def supervise(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def usage(self) -> dict[str, Any]: ...


class ParasailInference:
    """OpenAI-compatible Parasail client with bounded parallel inference."""

    def __init__(self):
        self.api_key = os.getenv("PARASAIL_API_KEY", "")
        self.base_url = os.getenv("PARASAIL_BASE_URL", "https://api.parasail.io/v1")
        self.model = os.getenv("PARASAIL_MODEL", "")
        if not self.api_key or not self.model:
            raise InferenceError("PARASAIL_API_KEY and PARASAIL_MODEL are required")
        concurrency = int(os.getenv("PARASAIL_MAX_CONCURRENCY", "8"))
        self.input_usd_per_million = float(
            os.getenv("PARASAIL_INPUT_USD_PER_MILLION", "0")
        )
        self.output_usd_per_million = float(
            os.getenv("PARASAIL_OUTPUT_USD_PER_MILLION", "0")
        )
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
        self._usage_lock = Lock()

    def _complete(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "store": False,
        }
        request = Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise InferenceError(f"Parasail inference failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise InferenceError(f"Parasail inference failed: {exc}") from exc
        try:
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise InferenceError("Parasail returned invalid structured output") from exc
        usage = result.get("usage", {})
        with self._usage_lock:
            self._usage["requests"] += 1
            self._usage["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
            self._usage["completion_tokens"] += int(
                usage.get("completion_tokens", 0)
            )
        return parsed

    async def _call(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._semaphore:
            return await asyncio.to_thread(self._complete, system, payload)

    async def specialist(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "You are the "
            f"{role} specialist in a UK freight quoting swarm. Analyze only your "
            "assigned evidence. Return JSON with summary, risk_flags (array), and "
            "confidence (0 to 1). Do not invent missing facts.",
            payload,
        )

    async def supervise(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "You supervise a human-gated UK freight quoting swarm. Return JSON with "
            "recommendation (APPROVE, PASS, or REVIEW), rationale, and confidence. "
            "Never claim the load is booked. Prefer REVIEW when evidence conflicts.",
            payload,
        )

    def usage(self) -> dict[str, Any]:
        with self._usage_lock:
            usage = dict(self._usage)
        usage["estimated_cost_usd"] = round(
            usage["prompt_tokens"] / 1_000_000 * self.input_usd_per_million
            + usage["completion_tokens"]
            / 1_000_000
            * self.output_usd_per_million,
            6,
        )
        usage["pricing_usd_per_million"] = {
            "input": self.input_usd_per_million,
            "output": self.output_usd_per_million,
        }
        return usage


class DemoInference:
    """Deterministic offline test double; it does not count as Parasail usage."""

    async def specialist(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        flags = payload.get("assessment", {}).get("flags") or payload.get(
            "assessment", {}
        ).get("risk_flags", [])
        return {
            "summary": f"Synthetic {role} assessment for offline verification.",
            "risk_flags": list(flags),
            "confidence": 0.8,
        }

    async def supervise(self, payload: dict[str, Any]) -> dict[str, Any]:
        eligible = bool(payload.get("deterministic_eligible"))
        return {
            "recommendation": "APPROVE" if eligible else "PASS",
            "rationale": "Synthetic supervisor output; not a live model decision.",
            "confidence": 0.8,
        }

    def usage(self) -> dict[str, Any]:
        return {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
