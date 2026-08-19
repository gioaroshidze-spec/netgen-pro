from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_is_pull_only_and_backend_is_not_published():
    compose = (ROOT / "deploy/docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "build:" not in compose
    assert "vnms-backend:${VNMS_RELEASE_TAG" in compose
    assert "vnms-backend:${VNMS_VERSION" not in compose
    backend_section, frontend_section = compose.split("  frontend:", 1)
    assert "ports:" not in backend_section
    assert "/var/run/docker.sock" not in compose
    assert "ports:" in frontend_section


def test_nginx_proxy_has_websocket_headers_and_safe_access_logging():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in nginx
    assert "location /ws/" in nginx
    assert "proxy_set_header Upgrade $http_upgrade" in nginx
    assert "proxy_set_header Connection $connection_upgrade" in nginx
    assert "$request_uri" not in nginx
    assert '"$request_method $uri $server_protocol"' in nginx
    websocket = nginx.split("location /ws/", 1)[1]
    assert "access_log off" in websocket


def test_deployment_scripts_have_strict_shell_mode_and_no_forbidden_commands():
    forbidden = ["docker compose down -v", "docker system prune", "chmod 777", "curl |", "eval "]
    for path in (ROOT / "deploy").glob("*.sh"):
        text = path.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text
        for value in forbidden:
            assert value not in text
