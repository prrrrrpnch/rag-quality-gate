from rqg.observability import tracing


def _f(x):
    return x + 1


def test_noop_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    assert not tracing.tracing_enabled()
    assert tracing.traceable("x")(_f) is _f  # identity: no wrapper, no network


def test_wraps_when_configured(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake-key-for-test")
    wrapped = tracing.traceable("x")(_f)
    assert wrapped is not _f  # langsmith wrapper applied (not called: would hit the network)
    meta = tracing.default_metadata()
    assert set(meta) == {"git_sha", "prompt_version", "dataset_version"}
