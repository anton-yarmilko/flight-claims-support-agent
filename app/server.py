"""Demo web app: chat agent, ticket reader, airline-reply analysis, claim letter.

    python -m app.server            # http://localhost:8000
    LLM_PROVIDER=groq LLM_API_KEY=... python -m app.server

Standard library only. Meant for local demos, not for the internet: there is no
auth and no rate limiting.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claims_agent import airline_reply, inbox  # noqa: E402
from claims_agent.agent import MISSING_KEYS, _reason, respond  # noqa: E402
from claims_agent.claim_letter import draft_letter  # noqa: E402
from claims_agent.facts import FlightFacts, check_facts  # noqa: E402
from claims_agent.i18n import LANGUAGES, native_names, strings, t  # noqa: E402
from claims_agent.llm import LLMError, get_llm  # noqa: E402
from claims_agent.ticket import read_ticket_image, read_ticket_text  # noqa: E402

INDEX = (Path(__file__).parent / "static" / "index.html").read_bytes()
MAX_BODY = 8 * 1024 * 1024
# Text caps keep prompts (and the LLM bill) small and stop someone pasting a book into the chat.
MAX_MESSAGE = 2000
MAX_DOCUMENT = 8000
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
FACT_FIELDS = ("origin", "destination", "airline", "flight_number", "date", "passenger", "booking_ref",
               "disruption", "delay_hours", "notice_days", "passengers", "via")

try:
    LLM_CLIENT = get_llm()
    LLM_PROBLEM = None
except LLMError as e:  # bad config: run offline and say why on the page
    LLM_CLIENT, LLM_PROBLEM = None, str(e)


LLM_PATHS = {"/api/chat", "/api/ticket", "/api/airline-reply", "/api/letter"}


class RateLimiter:
    """Sliding-window cap on LLM calls, per visitor and in total.

    The public demo pays for every LLM call, so one visitor (or a bot) must not
    burn the free quota. Over the limit the request still works, just with the
    offline templates instead of the LLM. Memory is per server process.
    """

    def __init__(self, per_client: int, total: int, window: float = 600.0) -> None:
        self.per_client, self.total, self.window = per_client, total, window
        self._hits: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        with self._lock:
            mine = self._hits.setdefault(client, deque())
            for q in (mine, self._all):
                while q and q[0] <= cutoff:
                    q.popleft()
            if len(mine) >= self.per_client or len(self._all) >= self.total:
                return False
            mine.append(now)
            self._all.append(now)
            if len(self._hits) > 10_000:  # drop idle visitors so memory stays small
                self._hits = {k: v for k, v in self._hits.items() if v}
            return True


LIMITER = RateLimiter(int(os.environ.get("LLM_RATE_PER_VISITOR", "40")),
                      int(os.environ.get("LLM_RATE_TOTAL", "600")),
                      float(os.environ.get("LLM_RATE_WINDOW_SECONDS", "600")))


def text_field(body: dict[str, Any], key: str, limit: int) -> str:
    text = str(body.get(key) or "").strip()
    if len(text) > limit:
        raise ValueError(f"{key} is too long ({limit} characters max)")
    return text


def clean_history(raw: Any) -> list[dict[str, str]]:
    """Last 12 turns, only user/assistant roles, each cut to MAX_MESSAGE characters."""
    if not isinstance(raw, list):
        return []
    turns = [{"role": m["role"], "content": str(m.get("content", ""))[:MAX_MESSAGE]}
             for m in raw if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    return turns[-12:]


def facts_from(d: dict[str, Any]) -> FlightFacts:
    f = FlightFacts()
    for k in FACT_FIELDS:
        v = d.get(k)
        if v in ("", None):
            continue
        if k == "delay_hours":
            v = float(v)
        elif k == "notice_days":
            v = int(v)
        elif k == "passengers":
            v = max(1, min(20, int(v)))
        elif k in {"origin", "destination", "airline", "booking_ref", "flight_number"}:
            v = str(v).strip().upper()
        elif k == "via":
            v = ",".join(re.findall(r"[A-Z]{3}", str(v).upper())[:3]) or None
        setattr(f, k, v)
    return f


def localize_check(d: dict[str, Any] | None, lang: str) -> dict[str, Any] | None:
    """Translate the check's reason and missing fields into the UI language."""
    if not d or lang not in LANGUAGES or lang == "en":
        return d
    d = dict(d)
    d["missing"] = [t(lang, MISSING_KEYS[m]) if m in MISSING_KEYS else m for m in d.get("missing", [])]
    if d.get("reason"):
        d["reason"] = _reason(lang, d["reason"])
    return d


def api(path: str, body: dict[str, Any], client: str = "local") -> dict[str, Any]:
    llm = LLM_CLIENT
    if llm and path in LLM_PATHS and not LIMITER.allow(client):
        out = _api(path, body, None)
        if isinstance(out, dict) and "mode" in out:
            out["mode"] = f"{out['mode']} (rate limit)"
        return out
    return _api(path, body, llm)


def _api(path: str, body: dict[str, Any], llm: Any) -> dict[str, Any]:
    if path == "/api/status":
        return {"llm": llm.model if llm else None, "vision": llm.vision_model if llm else None,
                "problem": LLM_PROBLEM}
    if path == "/api/chat":
        msg = text_field(body, "message", MAX_MESSAGE)
        if not msg:
            raise ValueError("message is empty")
        history = clean_history(body.get("history"))
        out = respond(msg, history, llm=llm, previous_handoffs=int(body.get("previous_handoffs", 0))).to_dict()
        out["eligibility"] = localize_check(out["eligibility"], str(body.get("lang", "en")))
        return out
    if path == "/api/ticket":
        if body.get("image"):
            raw = base64.b64decode(str(body["image"]).split(",", 1)[-1])
            return read_ticket_image(raw, str(body.get("mime") or "image/jpeg"), llm).to_dict()
        return read_ticket_text(text_field(body, "text", MAX_DOCUMENT), llm).to_dict()
    if path == "/api/eligibility":
        return localize_check(check_facts(facts_from(body)).to_dict(), str(body.get("lang", "en")))
    if path == "/api/airline-reply":
        return airline_reply.analyse(text_field(body, "text", MAX_DOCUMENT), llm).to_dict()
    if path == "/api/inbox":
        lines = body.get("messages")
        items = ([{"message": str(m)[:MAX_MESSAGE]} for m in lines if str(m).strip()] if isinstance(lines, list) and lines
                 else inbox.sample_messages())
        return inbox.process(items)
    if path == "/api/letter":
        return draft_letter(facts_from(body), llm=llm).to_dict()
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "FlyClaimDemo/1.0"

    def _send(self, status: int, payload: bytes, ctype: str) -> None:
        self.send_response(status)
        started = getattr(self, "_started", None)
        if started is not None:  # how long the app took, visible in the browser's network panel
            self.send_header("Server-Timing", f"app;dur={(time.perf_counter() - started) * 1000:.0f}")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _client(self) -> str:
        """Visitor id for the rate limit: first X-Forwarded-For hop behind a proxy, else the socket address."""
        fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or self.client_address[0]

    def do_GET(self) -> None:
        self._started = time.perf_counter()
        if self.path == "/api/health":
            llm = LLM_CLIENT
            self._json(200, {"ok": True, "llm": llm.model if llm else None,
                             "llm_cache": {"size": len(llm._cache), "hits": llm.hits} if llm else None})
        elif self.path in ("/", "/index.html"):
            self._send(200, INDEX, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._json(200, api("/api/status", {}))
        elif self.path == "/api/languages":
            self._json(200, native_names())
        elif self.path.startswith("/api/i18n/") and self.path[10:] in LANGUAGES:
            self._json(200, strings(self.path[10:]))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        self._started = time.perf_counter()
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large (8 MB max)"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("JSON object expected")
            self._json(200, api(self.path, body, self._client()))
        except KeyError:
            self._json(404, {"error": "unknown endpoint"})
        except (ValueError, TypeError) as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # keep the demo alive and show what broke
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"{self.command} {self.path}\n")


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    mode = f"LLM: {LLM_CLIENT.model}" if LLM_CLIENT else f"offline mode{f' ({LLM_PROBLEM})' if LLM_PROBLEM else ''}"
    print(f"FlyClaim AI demo on http://{host}:{port}  [{mode}]")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
