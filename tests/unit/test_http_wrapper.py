import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def server(settings):
    import serve_assistant

    serve_assistant.APP = serve_assistant.App()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve_assistant.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _post(url, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_chat_and_health(server):
    with urllib.request.urlopen(server + "/health") as r:
        assert json.loads(r.read())["mode"] == "mock"
    code, body = _post(
        server + "/chat",
        {"message": "What is the dustbin capacity of the RoboSweep S7?", "prompt_version": "v2"},
    )
    assert code == 200 and body["prompt_version"] == "v2" and "answer" in body
    assert _post(server + "/chat", {"nope": 1})[0] == 400
    assert _post(server + "/chat", {"message": "x", "prompt_version": "v9"})[0] == 400
    assert _post(server + "/other", {})[0] == 404
