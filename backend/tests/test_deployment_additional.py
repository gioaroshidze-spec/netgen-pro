import io
import zipfile


def test_readiness_failure_is_explicit(monkeypatch):
    from routers import system

    class BrokenEngine:
        def connect(self):
            raise OSError("test database unavailable")

    monkeypatch.setattr(system, "engine", BrokenEngine())
    result = system.readiness_snapshot()
    assert result["status"] == "not_ready"
    assert result["database"] == "error"
    assert "test database unavailable" in result["detail"]


def test_support_bundle_route_remains_admin_only():
    from routers.auth import get_current_admin
    from routers.logs import router

    route = next(route for route in router.routes if route.path == "/logs/support-bundle")
    assert any(dependency.call is get_current_admin for dependency in route.dependant.dependencies)


def test_support_bundle_handles_missing_log_files(tmp_path, monkeypatch):
    monkeypatch.setenv("VNMS_LOG_DIR", str(tmp_path / "missing"))
    from support_bundle import build_support_bundle

    with zipfile.ZipFile(io.BytesIO(build_support_bundle([]))) as archive:
        assert archive.read("logs/backend.log") == b"Log file is unavailable.\n"
        assert archive.read("logs/ansible.log") == b"Log file is unavailable.\n"
