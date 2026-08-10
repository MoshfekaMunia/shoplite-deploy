import asyncio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "user-service",
    "catalog-service",
    "order-service",
    "notification-service",
)


def service_source(service: str) -> str:
    return (ROOT / "services" / service / "app" / "main.py").read_text(encoding="utf-8")


def load_service(service: str):
    module_name = f"shoplite_test_{service.replace('-', '_')}"
    path = ROOT / "services" / service / "app" / "main.py"
    spec = spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_all_four_services_have_required_health_endpoints() -> None:
    for service in SERVICES:
        source = service_source(service)
        assert '@router.get("/healthz")' in source
        assert '@router.get("/readyz")' in source


def test_liveness_does_not_require_external_dependencies() -> None:
    async def request_health(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/healthz")

    for service in SERVICES:
        module = load_service(service)
        response = asyncio.run(request_health(module.app))
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_every_service_has_a_multistage_dockerfile() -> None:
    for service in SERVICES:
        dockerfile = (ROOT / "services" / service / "Dockerfile").read_text(
            encoding="utf-8"
        )
        assert dockerfile.count("FROM ") == 2
        assert ":latest" not in dockerfile
        assert "USER shoplite" in dockerfile


def test_order_queue_name_matches_consumer() -> None:
    order_source = service_source("order-service")
    notification_source = service_source("notification-service")
    assert '"order-created"' in order_source
    assert '"order-created"' in notification_source


def test_frontend_is_plain_html_css_and_javascript() -> None:
    frontend = ROOT / "services" / "user-service" / "frontend"
    assert (frontend / "index.html").is_file()
    assert (frontend / "styles.css").is_file()
    assert (frontend / "app.js").is_file()
    assert "node_modules" not in {path.name for path in frontend.iterdir()}


def test_compose_defines_exactly_the_assignment_containers() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    expected = {
        "user-service",
        "catalog-service",
        "order-service",
        "notification-service",
        "user-db",
        "catalog-db",
        "order-db",
        "notification-db",
        "rabbitmq",
    }
    assert set(compose["services"]) == expected
