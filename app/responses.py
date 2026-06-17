"""
Shared response helpers.
Every successful response is wrapped in the standard envelope:

  Single object:
    { "data": {...}, "meta": { "timestamp": "..." } }

  List:
    { "data": [...], "meta": { "total": n, "page": 1, "per_page": 20, "timestamp": "..." } }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_response(data: Any) -> dict:
    return {
        "data": data,
        "meta": {"timestamp": _now_iso()},
    }


def list_response(
    data: list,
    total: int,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    return {
        "data": data,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "timestamp": _now_iso(),
        },
    }
