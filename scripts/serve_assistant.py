#!/usr/bin/env python
"""Minimal HTTP wrapper around the assistant (stdlib only) for promptfoo.

POST /chat  {"message": str, "session_id"?: str, "prompt_version"?: "v1"|"v2", "model"?: str}
         -> {"answer", "refused", "cited_sources", "tool_calls", "guardrail_flags", "model", ...}
GET  /health

In mock mode every `model` maps to the same deterministic mock (stated in the response).
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _bootstrap  # noqa: F401
from rqg.config import get_settings
from rqg.llm.factory import build_app_llm
from rqg.observability.logger import InteractionLogger
from rqg.rag.assistant import SupportAssistant
from rqg.rag.prompts import PROMPTS
from rqg.rag.retriever import Retriever

_lock = threading.Lock()


class App:
    def __init__(self) -> None:
        self.s = get_settings()
        self.retriever = Retriever.from_corpus(self.s.corpus_dir, self.s.embedding_backend)
        self.logger = InteractionLogger(self.s.log_dir)
        self.cache: dict[tuple[str, str], SupportAssistant] = {}

    def assistant(self, prompt_version: str, model: str | None) -> SupportAssistant:
        key = (prompt_version, model or self.s.app_model)
        if key not in self.cache:
            s = self.s.model_copy(update={"app_model": key[1]})
            self.cache[key] = SupportAssistant(
                build_app_llm(s), self.retriever, s, self.logger, True, PROMPTS[prompt_version]
            )
        return self.cache[key]


APP: App | None = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send(200, {"ok": True, "mode": APP.s.mode}) if self.path == "/health" else self._send(
            404, {}
        )

    def do_POST(self) -> None:
        if self.path != "/chat":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            msg = str(req["message"])
            pv = str(req.get("prompt_version", "v1"))
            if pv not in PROMPTS:
                return self._send(400, {"error": f"unknown prompt_version {pv}"})
        except (KeyError, json.JSONDecodeError, ValueError) as e:
            return self._send(400, {"error": f"bad request: {e}"})
        with _lock:
            r = APP.assistant(pv, req.get("model")).ask(msg, session_id=req.get("session_id"))
        body = r.to_dict()
        body["mode"] = APP.s.mode
        body["prompt_version"] = pv
        self._send(200, body)

    def log_message(self, *args) -> None:  # keep promptfoo output clean
        pass


def main() -> None:
    global APP
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    APP = App()
    print(f"serving on http://127.0.0.1:{a.port} (mode={APP.s.mode})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
