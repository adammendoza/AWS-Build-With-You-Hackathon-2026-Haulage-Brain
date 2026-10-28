from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Citation, FreightLoad, MarketInputs


class GroundingError(RuntimeError):
    pass


class GroundingClient(Protocol):
    async def market_inputs(self, load: FreightLoad) -> MarketInputs: ...


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _extract_citations(value: Any) -> list[Citation]:
    citations: list[Citation] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            url = item.get("url") or item.get("link")
            if isinstance(url, str) and url.startswith("http"):
                snippet = item.get("snippet") or item.get("description") or ""
                if isinstance(snippet, list):
                    snippet = " ".join(str(part) for part in snippet)
                citations.append(
                    Citation(
                        title=str(item.get("title") or url),
                        url=url,
                        snippet=str(snippet)[:500],
                    )
                )
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    unique: dict[str, Citation] = {}
    for item in citations:
        unique.setdefault(item.url, item)
    return list(unique.values())


def _extract_diesel_price(payload: Any) -> float:
    patterns = (
        re.compile(
            r"diesel.{0,80}?(\d{2,3}(?:\.\d+)?)\s*(?:p|pence)\s*(?:per\s+litre|/\s*litre|a\s+litre)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\d{2,3}(?:\.\d+)?)\s*(?:p|pence)\s*(?:per\s+litre|/\s*litre|a\s+litre).{0,80}?diesel",
            re.IGNORECASE,
        ),
    )
    joined = "\n".join(_strings(payload))
    for pattern in patterns:
        for match in pattern.finditer(joined):
            value = float(match.group(1))
            if 50 <= value <= 300:
                return value
    raise GroundingError(
        "You.com results did not contain a parseable UK diesel pence-per-litre value"
    )


def _extract_gbp_charge(payload: Any, *, default: float = 0.0) -> float:
    joined = "\n".join(_strings(payload))
    for match in re.finditer(r"£\s*(\d{1,3}(?:\.\d{1,2})?)", joined):
        value = float(match.group(1))
        if 1 <= value <= 500:
            return value
    return default


class YouSearchGrounding:
    """Fetches current facts from You.com; never substitutes an invented price."""

    def __init__(self, *, api_key: str | None = None, search_url: str | None = None):
        self.api_key = api_key or os.getenv("YDC_API_KEY", "")
        self.search_url = search_url or os.getenv(
            "YDC_SEARCH_URL", "https://ydc-index.io/v1/search"
        )
        if not self.api_key:
            raise GroundingError("YDC_API_KEY is required for live grounding")
        self._diesel: tuple[float, list[Citation]] | None = None
        self._lock = asyncio.Lock()

    def _search(self, query: str, *, count: int = 8) -> dict[str, Any]:
        body = json.dumps(
            {
                "query": query,
                "count": count,
                "country": "GB",
                "language": "EN",
                "extraction": {"extraction_mode": "highlights"},
            }
        ).encode("utf-8")
        request = Request(
            self.search_url,
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            retry = exc.headers.get("Retry-After", "")
            raise GroundingError(
                f"You.com search failed with HTTP {exc.code}"
                + (f"; retry after {retry}s" if retry else "")
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GroundingError(f"You.com search failed: {exc}") from exc

    async def _current_diesel(self) -> tuple[float, list[Citation]]:
        async with self._lock:
            if self._diesel is None:
                payload = await asyncio.to_thread(
                    self._search,
                    "current average UK diesel price pence per litre latest RAC fuel watch",
                )
                self._diesel = (_extract_diesel_price(payload), _extract_citations(payload))
            return self._diesel

    async def market_inputs(self, load: FreightLoad) -> MarketInputs:
        diesel_price, diesel_citations = await self._current_diesel()
        has_ulez = load.ulez_flagged
        if has_ulez:
            query = (
                "current official London ULEZ daily charge van eligibility and charge "
                "site:tfl.gov.uk"
            )
        else:
            query = (
                f"current commercial vehicle road restrictions route {load.origin} "
                f"to {load.destination} UK official"
            )
        route_payload = await asyncio.to_thread(self._search, query)
        route_citations = _extract_citations(route_payload)
        route_text = " ".join(_strings(route_payload))[:1200]
        charge = _extract_gbp_charge(route_payload) if has_ulez else 0.0
        if has_ulez and charge <= 0:
            raise GroundingError("ULEZ is flagged but no current charge was grounded")
        return MarketInputs(
            diesel_price_ppl=diesel_price,
            restriction_summary=route_text,
            ulez_charge_gbp=charge,
            retrieved_at=datetime.now(timezone.utc),
            citations=tuple((diesel_citations + route_citations)[:10]),
        )


class DemoGrounding:
    """Deterministic synthetic grounding for tests; never presented as live."""

    def __init__(self, diesel_price_ppl: float = 145.0, ulez_charge_gbp: float = 12.5):
        self.diesel_price_ppl = diesel_price_ppl
        self.ulez_charge_gbp = ulez_charge_gbp

    async def market_inputs(self, load: FreightLoad) -> MarketInputs:
        has_ulez = load.ulez_flagged
        return MarketInputs(
            diesel_price_ppl=self.diesel_price_ppl,
            restriction_summary="Synthetic route facts for offline tests only.",
            ulez_charge_gbp=self.ulez_charge_gbp if has_ulez else 0.0,
            retrieved_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
            citations=(
                Citation(
                    title="Synthetic offline fixture",
                    url="fixture://market-inputs",
                    snippet="Not live web data.",
                ),
            ),
            source="synthetic-demo",
        )
