import pytest
import httpx
from api.main import app


@pytest.fixture
async def client():
    """AsyncClient with FastAPI app mounted in-process."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as c:
        yield c
