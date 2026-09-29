import pytest
from fastapi import FastAPI, Header, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class RangeFilter(BaseModel):
    min: int = 0
    max: int = 100


class FilterParams(BaseModel):
    name: str = "all"
    range: RangeFilter = Field(default_factory=RangeFilter)


app = FastAPI()


@app.get("/items/")
async def read_items(filter: FilterParams = Query(style="deepObject")):
    return filter


@app.get("/mixed/{filter}")
async def read_mixed(
    filter: str,
    query_filter: FilterParams = Query(style="deepObject", alias="filter"),
    x_filter: str = Header("none", alias="filter"),
):
    return {
        "path": filter,
        "query": query_filter.model_dump(),
        "header": x_filter,
    }


@app.get("/plain/")
async def read_plain(filter: str | None = None):
    return {"filter": filter}


client = TestClient(app)


def test_conflicting_scalar_and_object_at_root():
    response = client.get("/items/", params=[("filter", "a"), ("filter[name]", "b")])
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "Conflicting deepObject values: cannot mix a scalar value and an object for key: 'filter'",
                "input": "b",
            }
        ]
    }


def test_conflicting_scalar_and_object_nested():
    response = client.get(
        "/items/", params=[("filter[range]", "1"), ("filter[range][min]", "2")]
    )
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "Conflicting deepObject values: cannot mix a scalar value and an object for key: 'filter[range][min]'",
                "input": "2",
            }
        ]
    }


def test_conflicting_object_and_scalar_nested():
    response = client.get(
        "/items/", params=[("filter[range][min]", "2"), ("filter[range]", "1")]
    )
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "Conflicting deepObject values: cannot mix a scalar value and an object for key: 'filter[range]'",
                "input": "1",
            }
        ]
    }


def test_repeated_leaf_key_is_an_array():
    response = client.get(
        "/items/", params=[("filter[name]", "a"), ("filter[name]", "b")]
    )
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "deepObject query parameters do not support arrays",
                "input": "b",
            }
        ]
    }


def test_empty_segment_is_an_array():
    response = client.get("/items/", params={"filter[name][]": "a"})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "deepObject query parameters do not support arrays",
                "input": "a",
            }
        ]
    }


def test_invalid_deep_object_key():
    response = client.get("/items/", params={"filter[name": "a"})
    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": [
            {
                "type": "deep_object_parsing",
                "loc": ["query", "filter"],
                "msg": "Invalid deepObject key: 'filter[name'",
                "input": "a",
            }
        ]
    }


def test_parameter_namespaces_are_isolated():
    response = client.get(
        "/mixed/path-value",
        params={"filter[name]": "a", "filter[range][min]": "3"},
        headers={"filter": "header-value"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "path": "path-value",
        "query": {"name": "a", "range": {"min": 3, "max": 100}},
        "header": "header-value",
    }


def test_bracket_keys_are_plain_query_params_without_style():
    response = client.get("/plain/", params={"filter[name]": "a"})
    assert response.status_code == 200, response.text
    assert response.json() == {"filter": None}


def test_invalid_style_raises():
    with pytest.raises(ValueError, match="Invalid query parameter style"):
        Query(style="deep_object")
