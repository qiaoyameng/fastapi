import pytest
from fastapi import Depends, FastAPI, Response
from fastapi.exceptions import FastAPIError, ResponseValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class ItemHeaders(BaseModel):
    x_token: str = Field(alias="X-Token")
    x_count: int = Field(alias="X-Count")
    x_optional: str | None = Field(default=None, alias="X-Optional")


class CookieHeaders(BaseModel):
    set_cookie: list[str] = Field(alias="Set-Cookie")


class MultiHeaders(BaseModel):
    x_multi: list[str] = Field(alias="X-Multi")


class MarkerHeaders(BaseModel):
    x_marker: str = Field(alias="X-Marker")


class Item(BaseModel):
    name: str


app = FastAPI()


@app.get("/items", response_headers_model=ItemHeaders)
def get_items(response: Response):
    response.headers["X-Token"] = "secret-token"
    response.headers["X-Count"] = "42"
    return {"name": "portal-gun"}


@app.get("/items-missing-header", response_headers_model=ItemHeaders)
def get_items_missing_header(response: Response):
    response.headers["X-Count"] = "42"
    return {"name": "portal-gun"}


@app.get("/items-bad-int", response_headers_model=ItemHeaders)
def get_items_bad_int(response: Response):
    response.headers["X-Token"] = "secret-token"
    response.headers["X-Count"] = "not-an-int"
    return {"name": "portal-gun"}


@app.get("/items-cookies", response_headers_model=CookieHeaders)
def get_items_cookies(response: Response):
    response.set_cookie("session", "abc")
    response.set_cookie("tracker", "xyz")
    return {"name": "portal-gun"}


@app.get("/items-multi", response_headers_model=MultiHeaders)
def get_items_multi(response: Response):
    response.headers.append("X-Multi", "one")
    response.headers.append("X-Multi", "two")
    return {"name": "portal-gun"}


@app.get(
    "/items-body-ok-header-missing",
    response_model=Item,
    response_headers_model=MarkerHeaders,
)
def get_items_body_ok_header_missing():
    return {"name": "valid-body"}


@app.head("/items-head", response_headers_model=MarkerHeaders)
def head_items(response: Response):
    response.headers["X-Marker"] = "present"
    return None


@app.head("/items-head-missing", response_headers_model=MarkerHeaders)
def head_items_missing():
    return None


@app.get("/items-no-content", status_code=204, response_headers_model=MarkerHeaders)
def get_items_no_content(response: Response):
    response.headers["X-Marker"] = "present"
    return None


@app.get(
    "/items-no-content-missing", status_code=204, response_headers_model=MarkerHeaders
)
def get_items_no_content_missing():
    return None


def set_dependency_headers(response: Response):
    response.headers["X-Dep"] = "from-dependency"
    response.set_cookie("dep-cookie", "dep-value")


class DirectHeaders(BaseModel):
    x_dep: str = Field(alias="X-Dep")
    x_direct: str = Field(alias="X-Direct")
    set_cookie: list[str] = Field(alias="Set-Cookie")


@app.get(
    "/items-direct",
    response_headers_model=DirectHeaders,
    dependencies=[Depends(set_dependency_headers)],
)
def get_items_direct():
    response = Response(content="direct", media_type="text/plain")
    response.headers["X-Direct"] = "from-endpoint"
    # The header set directly on the returned response takes precedence over
    # the one written by the dependency
    response.headers["X-Dep"] = "from-endpoint"
    response.set_cookie("endpoint-cookie", "endpoint-value")
    return response


@app.get(
    "/items-direct-missing",
    response_headers_model=DirectHeaders,
)
def get_items_direct_missing():
    return Response(content="direct", media_type="text/plain")


client = TestClient(app)


def test_valid_headers():
    response = client.get("/items")
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "portal-gun"}
    assert response.headers["X-Token"] == "secret-token"
    assert response.headers["X-Count"] == "42"


def test_missing_required_header():
    with pytest.raises(ResponseValidationError) as exc_info:
        client.get("/items-missing-header")
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"] == ("response_headers", "X-Token")


def test_invalid_int_header():
    with pytest.raises(ResponseValidationError) as exc_info:
        client.get("/items-bad-int")
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "int_parsing"
    assert errors[0]["loc"] == ("response_headers", "X-Count")


def test_multiple_set_cookie_headers_preserved():
    response = client.get("/items-cookies")
    assert response.status_code == 200, response.text
    set_cookies = response.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    assert any(cookie.startswith("session=abc") for cookie in set_cookies)
    assert any(cookie.startswith("tracker=xyz") for cookie in set_cookies)


def test_repeated_header_lines():
    response = client.get("/items-multi")
    assert response.status_code == 200, response.text
    assert response.headers.get_list("x-multi") == ["one", "two"]


def test_body_valid_but_headers_invalid():
    with pytest.raises(ResponseValidationError) as exc_info:
        client.get("/items-body-ok-header-missing")
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"] == ("response_headers", "X-Marker")


def test_head_request_headers_validated():
    response = client.head("/items-head")
    assert response.status_code == 200, response.text
    assert response.headers["X-Marker"] == "present"


def test_head_request_missing_header():
    with pytest.raises(ResponseValidationError):
        client.head("/items-head-missing")


def test_no_content_headers_validated():
    response = client.get("/items-no-content")
    assert response.status_code == 204, response.text
    assert response.headers["X-Marker"] == "present"


def test_no_content_missing_header():
    with pytest.raises(ResponseValidationError):
        client.get("/items-no-content-missing")


def test_direct_response_headers_merged_and_validated():
    response = client.get("/items-direct")
    assert response.status_code == 200, response.text
    # Headers set directly on the returned response take precedence
    assert response.headers["X-Dep"] == "from-endpoint"
    assert response.headers["X-Direct"] == "from-endpoint"
    # Set-Cookie headers from the dependency and the endpoint are all kept, on
    # their own lines
    set_cookies = response.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    assert any(cookie.startswith("dep-cookie=dep-value") for cookie in set_cookies)
    assert any(
        cookie.startswith("endpoint-cookie=endpoint-value") for cookie in set_cookies
    )


def test_direct_response_headers_validated():
    with pytest.raises(ResponseValidationError):
        client.get("/items-direct-missing")


def test_openapi_response_headers():
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()
    headers = schema["paths"]["/items"]["get"]["responses"]["200"]["headers"]
    assert headers["X-Token"] == {
        "required": True,
        "schema": {"title": "X-Token", "type": "string"},
    }
    assert headers["X-Count"] == {
        "required": True,
        "schema": {"title": "X-Count", "type": "integer"},
    }
    assert "required" not in headers["X-Optional"]
    cookie_headers = schema["paths"]["/items-cookies"]["get"]["responses"]["200"][
        "headers"
    ]
    assert cookie_headers["Set-Cookie"]["required"] is True
    assert cookie_headers["Set-Cookie"]["schema"]["type"] == "array"
    no_content_headers = schema["paths"]["/items-no-content"]["get"]["responses"][
        "204"
    ]["headers"]
    assert no_content_headers["X-Marker"]["required"] is True


def test_router_level_response_headers_model():
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/routed", response_headers_model=MarkerHeaders)
    def get_routed(response: Response):
        response.headers["X-Marker"] = "present"
        return {}

    router_app = FastAPI()
    router_app.include_router(router)
    router_client = TestClient(router_app)
    response = router_client.get("/routed")
    assert response.status_code == 200, response.text
    assert response.headers["X-Marker"] == "present"


def test_invalid_response_headers_model():
    from fastapi import APIRouter

    router = APIRouter()
    with pytest.raises(FastAPIError):

        @router.get("/invalid", response_headers_model=dict)
        def get_invalid():
            return {}  # pragma: no cover
