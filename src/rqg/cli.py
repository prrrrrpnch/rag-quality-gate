"""`rqg` console entry point: ask the assistant from the terminal.

rqg ask "What is the filter life of the AeroPure 500?"
rqg chat            # interactive multi-turn session
"""

from __future__ import annotations

import argparse
import sys

from rqg.config import get_settings
from rqg.rag.assistant import build_assistant


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rqg")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    sub.add_parser("chat")
    a = ap.parse_args(argv)
    s = get_settings()
    asst = build_assistant(s)
    print(f"(mode={s.mode})", file=sys.stderr)
    if a.cmd == "ask":
        r = asst.ask(a.question)
        print(r.answer)
        return 0
    while True:
        try:
            q = input("you> ").strip()
        except EOFError:
            return 0
        if q in {"", "exit", "quit"}:
            return 0
        print("bot>", asst.ask(q, session_id="cli").answer)


if __name__ == "__main__":
    raise SystemExit(main())
