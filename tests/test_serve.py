"""Tests for OCBS restore URL and server lifecycle helpers."""

import socket

from ocbs import serve


def get_free_port() -> int:
    """Reserve a free localhost port for test server startup."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


def test_start_restore_server_reuses_running_instance():
    """Repeated startup on the same port reuses the existing server."""
    port = get_free_port()
    server = serve.start_restore_server(port=port)

    try:
        same_server = serve.start_restore_server(port=port)
        assert same_server is server
    finally:
        serve.shutdown_restore_server()


def test_start_restore_server_restarts_for_new_port():
    """Starting on a new port shuts down the old server and creates a new one."""
    first_port = get_free_port()
    second_port = get_free_port()
    server = serve.start_restore_server(port=first_port)

    try:
        replacement = serve.start_restore_server(port=second_port)
        assert replacement is not server
        assert replacement.server_port == second_port
    finally:
        serve.shutdown_restore_server()
