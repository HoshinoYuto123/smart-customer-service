from fastapi.testclient import TestClient

from app.main import app


def test_root_redirects_to_versioned_chat_ui():
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/static/chat.html?v=20260722-phase3"


def test_chat_ui_disables_browser_cache():
    with TestClient(app) as client:
        response = client.get("/static/chat.html")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
