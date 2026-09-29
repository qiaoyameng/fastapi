from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile as StarletteUploadFile

app = FastAPI()


class Item(BaseModel):
    name: str
    price: float


@app.post("/items/")
def create_item(
    meta: Annotated[Item, Form(content_type="application/json")],
    note: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    return {"meta": meta, "note": note, "filename": file.filename}


@app.post("/items-list/")
def create_items(
    items: Annotated[list[Item], Form(content_type="application/json")],
):
    return {"items": items}


@app.post("/aliased/")
def create_aliased(
    data: Annotated[Item, Form(alias="itemData", content_type="application/json")],
):
    return {"data": data}


default_item = Item(name="default", price=0.0)


@app.post("/with-default/")
def create_with_default(
    meta: Annotated[Item, Form(content_type="application/json")] = default_item,
    items: Annotated[list[Item], Form(content_type="application/json")] = [],
):
    return {"meta": meta, "items": items}


client = TestClient(app)


def test_json_text_part_decoded_to_model():
    response = client.post(
        "/items/",
        data={"meta": '{"name": "portal-gun", "price": 42.0}', "note": "not json"},
        files={"file": ("file.txt", b"content")},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "meta": {"name": "portal-gun", "price": 42.0},
        "note": "not json",
        "filename": "file.txt",
    }


def test_json_part_with_filename_decoded_to_model():
    response = client.post(
        "/items/",
        data={"note": "hello"},
        files={
            "meta": ("meta.json", '{"name": "plumbus", "price": 6.5}', "application/json"),
            "file": ("file.txt", b"content"),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "meta": {"name": "plumbus", "price": 6.5},
        "note": "hello",
        "filename": "file.txt",
    }


def test_other_text_fields_keep_original_handling():
    # A plain Form() field is not decoded, even if its content looks like JSON
    response = client.post(
        "/items/",
        data={"meta": '{"name": "portal-gun", "price": 42.0}', "note": '{"a": 1}'},
        files={"file": ("file.txt", b"content")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["note"] == '{"a": 1}'


def test_invalid_json_text_part():
    response = client.post(
        "/items/",
        data={"meta": "not json", "note": "hi"},
        files={"file": ("file.txt", b"content")},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert response.json()["detail"][0]["loc"] == ["body", "meta"]


def test_nested_model_validation_error_loc():
    response = client.post(
        "/items/",
        data={"meta": '{"name": "portal-gun"}', "note": "hi"},
        files={"file": ("file.txt", b"content")},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "missing"
    assert response.json()["detail"][0]["loc"] == ["body", "meta", "price"]


def test_multiple_json_parts_form_model_list():
    response = client.post(
        "/items-list/",
        data=[
            ("items", '{"name": "portal-gun", "price": 42.0}'),
            ("items", '{"name": "plumbus", "price": 6.5}'),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [
            {"name": "portal-gun", "price": 42.0},
            {"name": "plumbus", "price": 6.5},
        ]
    }


def test_multiple_json_parts_with_filenames():
    response = client.post(
        "/items-list/",
        files=[
            ("items", ("a.json", '{"name": "portal-gun", "price": 42.0}', "application/json")),
            ("items", ("b.json", '{"name": "plumbus", "price": 6.5}', "application/json")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [
            {"name": "portal-gun", "price": 42.0},
            {"name": "plumbus", "price": 6.5},
        ]
    }


def test_invalid_json_in_list_part_points_to_part_index():
    response = client.post(
        "/items-list/",
        data=[
            ("items", '{"name": "portal-gun", "price": 42.0}'),
            ("items", "not json"),
        ],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert response.json()["detail"][0]["loc"] == ["body", "items", 1]


def test_nested_error_in_list_part_points_to_part_and_field():
    response = client.post(
        "/items-list/",
        data=[
            ("items", '{"name": "portal-gun", "price": 42.0}'),
            ("items", '{"name": "plumbus"}'),
        ],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "missing"
    assert response.json()["detail"][0]["loc"] == ["body", "items", 1, "price"]


def test_upload_file_released_on_json_decode_error(monkeypatch):
    closed_files: list[StarletteUploadFile] = []
    original_close = FormData.close

    async def spy_close(self: FormData) -> None:
        for _, value in self.multi_items():
            if isinstance(value, StarletteUploadFile):
                closed_files.append(value)
        await original_close(self)

    monkeypatch.setattr(FormData, "close", spy_close)
    response = client.post(
        "/items/",
        data={"meta": "not json", "note": "hi"},
        files={"file": ("file.txt", b"content")},
    )
    assert response.status_code == 422, response.text
    assert closed_files
    assert all(upload_file.file.closed for upload_file in closed_files)


def test_external_alias():
    response = client.post(
        "/aliased/",
        data={"itemData": '{"name": "portal-gun", "price": 42.0}'},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"data": {"name": "portal-gun", "price": 42.0}}


def test_external_alias_error_loc_uses_alias():
    response = client.post("/aliased/", data={"itemData": "not json"})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", "itemData"]


def test_default_value_used_when_part_missing():
    response = client.post("/with-default/", data={})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "meta": {"name": "default", "price": 0.0},
        "items": [],
    }


def test_default_value_overridden_by_part():
    response = client.post(
        "/with-default/",
        data={"meta": '{"name": "plumbus", "price": 6.5}'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"name": "plumbus", "price": 6.5}


def get_openapi() -> dict[str, Any]:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    return response.json()


def test_openapi_encoding_for_json_form_field():
    openapi = get_openapi()
    content = openapi["paths"]["/items/"]["post"]["requestBody"]["content"]
    assert "multipart/form-data" in content
    assert content["multipart/form-data"]["encoding"] == {
        "meta": {"contentType": "application/json"}
    }


def test_openapi_encoding_uses_external_alias():
    openapi = get_openapi()
    content = openapi["paths"]["/aliased/"]["post"]["requestBody"]["content"]
    media_type = next(iter(content))
    schema = content[media_type]["schema"]
    if "$ref" in schema:
        schema = openapi["components"]["schemas"][schema["$ref"].split("/")[-1]]
    assert "itemData" in schema["properties"]
    assert content[media_type]["encoding"] == {
        "itemData": {"contentType": "application/json"}
    }


def test_openapi_no_encoding_for_plain_form_fields():
    openapi = get_openapi()
    content = openapi["paths"]["/items/"]["post"]["requestBody"]["content"]
    encoding = content["multipart/form-data"]["encoding"]
    assert "note" not in encoding
    assert "file" not in encoding
