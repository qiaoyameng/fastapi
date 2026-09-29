from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel


class RangeFilter(BaseModel):
    min: int = 0
    max: int = 10


class FilterParams(BaseModel):
    name: str = "all"
    range: RangeFilter = RangeFilter()


class TagParams(BaseModel):
    model_config = {"extra": "forbid"}

    tag: str


app = FastAPI()


@app.get("/items/")
async def read_items(
    filter: Annotated[FilterParams, Query(style="deepObject")],
    q: str | None = None,
):
    return {"filter": filter.model_dump(), "q": q}


@app.get("/aliased/")
async def read_aliased(
    filter: Annotated[FilterParams, Query(style="deepObject", alias="f")],
):
    return filter.model_dump()


@app.get("/required/")
async def read_required(filter: Annotated[TagParams, Query(style="deepObject")]):
    return filter.model_dump()


@app.get("/two/")
async def read_two(
    filter: Annotated[FilterParams, Query(style="deepObject")],
    tags: Annotated[TagParams, Query(style="deepObject")],
):
    return {"filter": filter.model_dump(), "tags": tags.model_dump()}


@app.get("/plain/")
async def read_plain(filter: Annotated[FilterParams, Query()]):
    return filter.model_dump()


client = TestClient(app)


def test_deep_object_nested_model():
    response = client.get(
        "/items/",
        params=[("filter[name]", "a"), ("filter[range][min]", "3"), ("q", "x")],
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "filter": {"name": "a", "range": {"min": 3, "max": 10}},
        "q": "x",
    }


def test_deep_object_defaults():
    response = client.get("/items/")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "filter": {"name": "all", "range": {"min": 0, "max": 10}},
        "q": None,
    }


def test_deep_object_alias():
    response = client.get("/aliased/", params={"f[name]": "z"})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "z", "range": {"min": 0, "max": 10}}
    # Keys not prefixed with the alias are not part of the deep object
    response = client.get("/aliased/", params={"filter[name]": "z"})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "all", "range": {"min": 0, "max": 10}}


def test_deep_object_validation_error_location():
    response = client.get("/items/", params={"filter[range][min]": "not-an-int"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", "filter", "range", "min"]
    assert response.json()["detail"][0]["type"] == "int_parsing"


def test_deep_object_required_field():
    response = client.get("/required/")
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "missing"
    assert response.json()["detail"][0]["loc"] == ["query", "filter", "tag"]


def test_deep_object_model_validation_still_applies():
    response = client.get(
        "/required/", params={"filter[tag]": "x", "filter[nope]": "1"}
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
    assert response.json()["detail"][0]["loc"] == ["query", "filter", "nope"]


def test_deep_object_arrays_not_supported():
    response = client.get("/items/", params={"filter[name][]": "a"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "deep_object_array_not_supported"
    assert response.json()["detail"][0]["loc"] == ["query", "filter", "name", ""]


def test_deep_object_repeated_scalar_leaf():
    response = client.get(
        "/items/", params=[("filter[name]", "a"), ("filter[name]", "b")]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "deep_object_conflict"


@pytest.mark.parametrize(
    "params",
    [
        [("filter[name]", "a"), ("filter[name][sub]", "b")],
        [("filter[name][sub]", "b"), ("filter[name]", "a")],
        [("filter", "x"), ("filter[name]", "a")],
    ],
)
def test_deep_object_scalar_object_conflict(params: list[tuple[str, str]]):
    response = client.get("/items/", params=params)
    assert response.status_code == 422, response.text
    assert any(
        error["type"] == "deep_object_conflict"
        for error in response.json()["detail"]
    )


def test_deep_object_namespaces_do_not_overlap():
    response = client.get(
        "/two/", params={"filter[name]": "a", "tags[tag]": "t1"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "filter": {"name": "a", "range": {"min": 0, "max": 10}},
        "tags": {"tag": "t1"},
    }


def test_deep_object_disabled_keeps_plain_query_handling():
    # Without style="deepObject", bracket keys are plain (unknown) query
    # parameter names and don't populate the model
    response = client.get("/plain/", params={"filter[name]": "a", "name": "direct"})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "direct", "range": {"min": 0, "max": 10}}


def test_deep_object_openapi():
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()
    parameters = {
        parameter["name"]: parameter
        for parameter in schema["paths"]["/items/"]["get"]["parameters"]
    }
    assert parameters["filter"]["style"] == "deepObject"
    assert parameters["filter"]["explode"] is True
    assert parameters["filter"]["required"] is False
    assert parameters["filter"]["schema"] == {
        "$ref": "#/components/schemas/FilterParams"
    }
    assert "style" not in parameters["q"]
    required_parameters = schema["paths"]["/required/"]["get"]["parameters"]
    assert required_parameters[0]["required"] is True
    plain_parameters = schema["paths"]["/plain/"]["get"]["parameters"]
    assert all("style" not in parameter for parameter in plain_parameters)
    assert "FilterParams" in schema["components"]["schemas"]


def test_deep_object_requires_model():
    bad_app = FastAPI()
    with pytest.raises(AssertionError, match="must be a Pydantic model"):

        @bad_app.get("/bad/")
        async def bad(filter: Annotated[str, Query(style="deepObject")]):
            return {}  # pragma: no cover
