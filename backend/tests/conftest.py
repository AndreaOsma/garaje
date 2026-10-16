import os
import tempfile

# Base de datos aislada por ejecución: tiene que fijarse antes de importar app.*.
_tmp = tempfile.mkdtemp(prefix="garaje-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def vehicle(client):
    response = client.post("/api/vehicles", json={"name": "León", "make": "SEAT", "fuel_type": "diesel", "odometer_km": 100000})
    assert response.status_code == 201, response.text
    return response.json()
