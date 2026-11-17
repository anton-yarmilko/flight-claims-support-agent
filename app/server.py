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
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claims_agent import airline_reply  # noqa: E402
from claims_agent.agent import respond  # noqa: E402
from claims_agent.claim_letter import draft_letter  # noqa: E402
from claims_agent.facts import FlightFacts, check_facts  # noqa: E402
from claims_agent.llm import LLMError, get_llm  # noqa: E402
from claims_agent.ticket import read_ticket_image, read_ticket_text  # noqa: E402

INDEX = (Path(__file__).parent / "static" / "index.html").read_bytes()
MAX_BODY = 8 * 1024 * 1024
FACT_FIELDS = ("origin", "destination", "airline", "flight_number", "date", "passenger", "booking_ref",
               "disruption", "delay_hours", "notice_days")

try:
    LLM_CLIENT = get_llm()
    LLM_PROBLEM = None
except LLMError as e:  # bad config: run offline and say why on the page
    LLM_CLIENT, LLM_PROBLEM = None, str(e)


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
        elif k in {"origin", "destination", "airline", "booking_ref", "flight_number"}:
            v = str(v).strip().upper()
        setattr(f, k, v)
    return f


def api(path: str, body: dict[str, Any]) -> dict[str, Any]:
    llm = LLM_CLIENT
    if path == "/api/status":
        return {"llm": llm.model if llm else None, "vision": llm.vision_model if llm else None,
                "problem": LLM_PROBLEM}
    if path == "/api/chat":
        msg = str(body.get("message", "")).strip()
        if not msg:
            raise ValueError("message is empty")
        history = [m for m in body.get("history", []) if isinstance(m, dict)][-12:]
        return respond(msg, history, llm=llm, previous_handoffs=int(body.get("previous_handoffs", 0))).to_dict()
    if path == "/api/ticket":
        if body.get("image"):
            raw = base64.b64decode(str(body["image"]).split(",", 1)[-1])
            return read_ticket_image(raw, str(body.get("mime") or "image/jpeg"), llm).to_dict()
        return read_ticket_text(str(body.get("text", "")), llm).to_dict()
    if path == "/api/eligibility":
        return check_facts(facts_from(body)).to_dict()
    if path == "/api/airline-reply":
        return airline_reply.analyse(str(body.get("text", "")), llm).to_dict()
    if path == "/api/letter":
        return draft_letter(facts_from(body), llm=llm).to_dict()
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "FlyClaimDemo/1.0"

    def _send(self, status: int, payload: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._json(200, api("/api/status", {}))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large (8 MB max)"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("JSON object expected")
            self._json(200, api(self.path, body))
        except KeyError:
            self._json(404, {"error": "unknown endpoint"})
        except (ValueError, TypeError) as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # keep the demo alive and show what broke
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (self.command, self.path))


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    mode = f"LLM: {LLM_CLIENT.model}" if LLM_CLIENT else f"offline mode{f' ({LLM_PROBLEM})' if LLM_PROBLEM else ''}"
    print(f"FlyClaim AI demo on http://{host}:{port}  [{mode}]")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
