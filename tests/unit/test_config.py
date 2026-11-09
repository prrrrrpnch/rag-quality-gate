from rqg.config import Settings, git_sha


def test_mock_when_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_LLM", "0")
    s = Settings(_env_file=None)
    assert not s.has_real_key
    assert s.use_mock and s.mode == "mock"


def test_real_mode_when_key_present(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    s = Settings(_env_file=None)
    assert s.has_real_key and not s.use_mock and s.mode == "real"
    assert "test-not-a-real-key" not in repr(s)  # SecretStr never prints


def test_mock_forced_even_with_key(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert Settings(_env_file=None).use_mock


def test_openai_provider_key(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert Settings(_env_file=None).has_real_key


def test_defaults_and_tracing(monkeypatch):
    monkeypatch.delenv("APP_MODEL", raising=False)
    s = Settings(_env_file=None)
    assert s.app_model == "claude-haiku-5-5"
    assert s.judge_model == "claude-sonnet-5-5"
    assert s.judge_repeats == 3
    assert not s.tracing_enabled


def test_git_sha_is_string():
    assert isinstance(git_sha(), str) and git_sha()


def test_git_sha_marks_dirty_tree(tmp_path, monkeypatch):
    import subprocess

    import rqg.config as cfg

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in {"user.email": "t@example.com", "user.name": "t"}.items():
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    (tmp_path / "f.txt").write_text("a")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    monkeypatch.setattr(cfg, "REPO_ROOT", tmp_path)
    clean = cfg.git_sha()
    assert clean and not clean.endswith("-dirty") and len(cfg.git_sha(short=False)) == 40
    (tmp_path / "f.txt").write_text("b")
    assert cfg.git_sha() == f"{clean}-dirty"
    monkeypatch.setattr(cfg, "REPO_ROOT", tmp_path / "nope")
    assert cfg.git_sha() == "unknown"
