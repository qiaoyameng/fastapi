import importlib

import pytest
from fastapi.testclient import TestClient

from tests.utils import needs_py310


@pytest.fixture(
    name="client",
    params=[
        pytest.param("tutorial003_py310", marks=[needs_py310]),
        pytest.param("tutorial003_an_py310", marks=[needs_py310]),
    ],
)
def get_client(request: pytest.FixtureRequest):
    mod = importlib.import_module(f"docs_src.query_param_models.{request.param}")

    client = TestClient(mod.app)
    return client


def test_deep_object_query_param_model(client: TestClient):
    response = client.get(
        "/items/",
        params=[("filter[name]", "a"), ("filter[range][min]", "3")],
    )
    assert response.status_code == 200
    assert response.json() == {
        "name": "a",
        "range": {"min": 3, "max": 100},
    }


def test_deep_object_defaults(client: TestClient):
    response = client.get("/items/")
    assert response.status_code == 200
    assert response.json() == {
        "name": "",
        "range": {"min": 0, "max": 100},
    }


def test_deep_object_invalid(client: TestClient):
    response = client.get("/items/", params={"filter[range][min]": "not-an-int"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "filter", "range", "min"]


def test_deep_object_openapi(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    parameters = response.json()["paths"]["/items/"]["get"]["parameters"]
    assert len(parameters) == 1
    parameter = parameters[0]
    assert parameter["name"] == "filter"
    assert parameter["in"] == "query"
    assert parameter["required"] is False
    assert parameter["style"] == "deepObject"
    assert parameter["explode"] is True
    assert parameter["schema"] == {"$ref": "#/components/schemas/FilterParams"}
