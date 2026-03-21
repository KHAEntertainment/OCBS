"""Tests for OCBS restore URL and server lifecycle helpers."""

from ocbs import serve


def test_generate_restore_url_uses_env_host(monkeypatch):
    """OCBS_SERVE_HOST overrides auto-detected restore host."""
    monkeypatch.setenv("OCBS_SERVE_HOST", "restore.example.test")
    url = serve.generate_restore_url("checkpoint-123", port=4567)

    assert url == "http://restore.example.test:4567/restore/checkpoint-123"


def test_generate_restore_url_uses_env_url_port(monkeypatch):
    """An explicit port in OCBS_SERVE_HOST is preserved."""
    monkeypatch.setenv("OCBS_SERVE_HOST", "https://restore.example.test:9443")
    url = serve.generate_restore_url("checkpoint-123", port=4567)

    assert url == "https://restore.example.test:9443/restore/checkpoint-123"
