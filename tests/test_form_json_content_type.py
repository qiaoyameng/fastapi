import tempfile
from typing import Annotated

import anyio
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.dependencies.utils import _extract_form_body
from fastapi.testclient import TestClient
from fastapi.utils import create_model_field
from pydantic import BaseModel
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile as StarletteUploadFile

app = FastAPI()


class Meta(BaseModel):
    name: str
    count: int = 3


@app.post("/items/")
async def create_item(
    file: Annotated[UploadFile, File()],
    meta: Annotated[Meta, Form(content_type="application/json")],
    note: Annotated[str, Form()] = "",
):
    return {"filename": file.filename, "meta": meta, "note": note}


@app.post("/items-list/")
async def create_items(
    meta: Annotated[list[Meta], Form(content_type="application/json")],
):
    return meta


@app.post("/items-alias/")
async def create_item_alias(
    meta: Annotated[
        Meta | None, Form(content_type="application/json", alias="itemMeta")
    ] = None,
):
    return meta


client = TestClient(app)


def test_json_part_with_filename():
    response = client.post(
        "/items/",
        files={
            "file": ("data.bin", b"binary", "application/octet-stream"),
            "meta": ("meta.json", '{"name": "rick"}', "application/json"),
        },
        data={"note": "plain text still works"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "filename": "data.bin",
        "meta": {"name": "rick", "count": 3},
        "note": "plain text still works",
    }


def test_json_part_plain_text():
    response = client.post(
        "/items/",
        files={"file": ("data.bin", b"binary")},
        data={"meta": '{"name": "morty", "count": 5}'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"name": "morty", "count": 5}


def test_json_part_plain_text_invalid_json():
    response = client.post(
        "/items/",
        files={"file": ("data.bin", b"binary")},
        data={"meta": "this is not json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert response.json()["detail"][0]["loc"] == ["body", "meta"]


def test_json_part_list():
    response = client.post(
        "/items-list/",
        files=[
            ("meta", ("a.json", '{"name": "a"}', "application/json")),
            ("meta", ("b.json", '{"name": "b", "count": 2}', "application/json")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json() == [
        {"name": "a", "count": 3},
        {"name": "b", "count": 2},
    ]


def test_json_part_list_nested_validation_error():
    response = client.post(
        "/items-list/",
        files=[
            ("meta", ("a.json", '{"name": "a"}', "application/json")),
            ("meta", ("b.json", '{"count": "x"}', "application/json")),
        ],
    )
    assert response.status_code == 422, response.text
    locs = [error["loc"] for error in response.json()["detail"]]
    assert ["body", "meta", 1, "name"] in locs
    assert ["body", "meta", 1, "count"] in locs


def test_json_part_list_decode_error():
    response = client.post(
        "/items-list/",
        files=[
            ("meta", ("a.json", '{"name": "a"}', "application/json")),
            ("meta", ("b.json", "not json", "application/json")),
        ],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert response.json()["detail"][0]["loc"] == ["body", "meta", 1]


def test_json_part_alias():
    response = client.post("/items-alias/", data={"itemMeta": '{"name": "summer"}'})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "summer", "count": 3}


def test_json_part_default():
    response = client.post("/items-alias/")
    assert response.status_code == 200, response.text
    assert response.json() is None


def test_openapi_encoding():
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    spec = response.json()
    items_content = spec["paths"]["/items/"]["post"]["requestBody"]["content"]
    assert items_content["multipart/form-data"]["encoding"] == {
        "meta": {"contentType": "application/json"}
    }
    assert "note" not in items_content["multipart/form-data"]["encoding"]
    list_content = spec["paths"]["/items-list/"]["post"]["requestBody"]["content"]
    assert list_content["application/x-www-form-urlencoded"]["encoding"] == {
        "meta": {"contentType": "application/json"}
    }
    alias_content = spec["paths"]["/items-alias/"]["post"]["requestBody"]["content"]
    assert alias_content["application/x-www-form-urlencoded"]["encoding"] == {
        "itemMeta": {"contentType": "application/json"}
    }


def _make_upload_file(content: bytes, filename: str) -> StarletteUploadFile:
    file = tempfile.SpooledTemporaryFile(max_size=1024)
    file.write(content)
    file.seek(0)
    return StarletteUploadFile(file=file, filename=filename)


def test_decode_failure_releases_received_files():
    field = create_model_field(
        name="meta",
        type_=list[Meta],
        field_info=Form(content_type="application/json", annotation=list[Meta]),
    )
    first = _make_upload_file(b'{"name": "ok"}', "a.json")
    second = _make_upload_file(b"not json", "b.json")
    form = FormData([("meta", first), ("meta", second)])

    async def extract():
        return await _extract_form_body([field], form)

    values, errors, failed_aliases = anyio.run(extract)
    assert values == {}
    assert failed_aliases == {"meta"}
    assert errors[0]["type"] == "json_invalid"
    assert errors[0]["loc"] == ("body", "meta", 1)
    assert first.file.closed
    assert second.file.closed
