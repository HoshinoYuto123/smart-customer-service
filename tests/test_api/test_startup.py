import pytest

from app.core.config import get_app_config
from app.main import app, lifespan


@pytest.mark.asyncio
async def test_production_rejects_default_auth_secret(monkeypatch):
    config = get_app_config()
    monkeypatch.setattr(config.app, "mode", "production")
    monkeypatch.setattr(config.auth, "secret", "local-demo-secret-change-me")

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        async with lifespan(app):
            pass
