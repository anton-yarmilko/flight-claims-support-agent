"""Vercel entry point: serves the demo as one Python function.

Every path is rewritten here (see vercel.json); the stdlib handler from
app/server.py does the routing. No LLM key is set on the public demo, so it
runs in offline mode and costs nothing per request.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.server import Handler  # noqa: E402


class handler(Handler):  # noqa: N801  Vercel looks for this exact name
    """vercel.json rewrites every path to /api/index?__p=<path>; restore it."""

    def _restore_path(self) -> None:
        from urllib.parse import parse_qs, urlsplit

        q = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if "__p" in q:
            self.path = "/" + q["__p"][0].lstrip("/")

    def do_GET(self) -> None:  # noqa: N802
        self._restore_path()
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._restore_path()
        super().do_POST()
