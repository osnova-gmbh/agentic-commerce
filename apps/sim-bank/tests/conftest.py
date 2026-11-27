import pytest
from fastapi.testclient import TestClient
from sim_bank import create_app


@pytest.fixture()
def http() -> TestClient:
    return TestClient(create_app())
