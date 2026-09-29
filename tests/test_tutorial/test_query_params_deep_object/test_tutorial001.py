import importlib

import pytest
from fastapi.testclient import TestClient

from tests.utils import needs_py310


@pytest.fixture(
    name="client",
    params=[
        pytest.param("tutorial001_py310", marks=needs_py310),
        pytest.param("tutorial001_an_py310", marks=needs_py310),
    ],
)
def get_client(request: pytest.FixtureRequest):
    mod = importlib.import_module(f"docs_src.query_params_deep_object.{request.param}")

    client = TestClient(mod.app)
    return client


def test_deep_object_query_params(client: TestClient):
    response = client.get(
        "/items/", params={"filter[name]": "a", "filter[range][min]": "3"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "name": "a",
        "orderBy": "created_at",
        "range": {"min": 3, "max": 100},
    }


def test_deep_object_query_params_defaults(client: TestClient):
    response = client.get("/items/")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "name": "all",
        "orderBy": "created_at",
        "range": {"min": 0, "max": 100},
    }


def test_deep_object_query_params_alias(client: TestClient):
    response = client.get("/items/", params={"filter[orderBy]": "updated_at"})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "name": "all",
        "orderBy": "updated_at",
        "range": {"min": 0, "max": 100},
    }


def test_deep_object_query_params_invalid(client: TestClient):
    response = client.get("/items/", params={"filter[range][min]": "notanint"})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "int_parsing",
                "loc": ["query", "filter", "range", "min"],
                "msg": "Input should be a valid integer, unable to parse string as an integer",
                "input": "notanint",
            }
        ]
    }


def test_deep_object_query_params_array_not_supported(client: TestClient):
    response = client.get("/items/", params={"filter[range][]": "1"})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "deepObject query parameters do not support arrays",
                "input": "1",
            }
        ]
    }


def test_openapi_schema(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    assert response.json()["paths"]["/items/"]["get"]["parameters"] == [
        {
            "name": "filter",
            "in": "query",
            "required": True,
            "schema": {"$ref": "#/components/schemas/FilterParams"},
            "style": "deepObject",
            "explode": True,
        }
    ]
