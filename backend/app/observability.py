from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class MetricsStore:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.timings: dict[str, list[float]] = defaultdict(list)

    def inc(self, key: str, value: int = 1) -> None:
        self.counters[key] += value

    def observe(self, key: str, value: float) -> None:
        self.timings[key].append(value)

    def snapshot(self) -> dict[str, object]:
        return {
            "counters": dict(self.counters),
            "timings": {k: {"count": len(v), "avg": (sum(v) / len(v)) if v else 0.0} for k, v in self.timings.items()},
        }


metrics = MetricsStore()


def get_logger() -> logging.Logger:
    logger = logging.getLogger("agentmonopoly")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


logger = get_logger()


def log_json(event: str, **payload: object) -> None:
    logger.info(json.dumps({"event": event, **payload}, ensure_ascii=False))


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("x-trace-id", f"trace-{uuid.uuid4().hex[:12]}")
        request.state.trace_id = trace_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["x-trace-id"] = trace_id
        metrics.observe("http.latency_ms", duration_ms)
        log_json(
            "http.request",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=round(duration_ms, 2),
        )
        return response
