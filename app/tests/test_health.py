import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_health_check():
    """
    Test that the /health endpoint responds successfully and reports
    that the database is connected.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"

@pytest.mark.asyncio
async def test_home_page_renders():
    """
    Test that the home page renders successfully and contains the correct HTML elements.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert "AURA" in response.text
    assert "Scaffold Status" in response.text
    assert "Available Personas" in response.text
