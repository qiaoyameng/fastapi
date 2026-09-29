import collections.abc
import re
import types
import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
)

import fastapi
from fastapi._compat import (
    ModelField,
    PydanticSchemaGenerationError,
    Undefined,
    annotation_is_pydantic_v1,
)
from fastapi.datastructures import DefaultPlaceholder, DefaultType
from fastapi.exceptions import (
    EndpointContext,
    FastAPIDeprecationWarning,
    PydanticV1NotSupportedError,
    ResponseValidationError,
)
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ._compat import v2

if TYPE_CHECKING:  # pragma: nocover
    from .routing import APIRoute


def is_body_allowed_for_status_code(status_code: int | str | None) -> bool:
    if status_code is None:
        return True
    # Ref: https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.1.0.md#patterned-fields-1
    if status_code in {
        "default",
        "1XX",
        "2XX",
        "3XX",
        "4XX",
        "5XX",
    }:
        return True
    current_status_code = int(status_code)
    return not (current_status_code < 200 or current_status_code in {204, 205, 304})


def get_path_param_names(path: str) -> set[str]:
    return set(re.findall("{(.*?)}", path))


_invalid_args_message = (
    "Invalid args for response field! Hint: "
    "check that {type_} is a valid Pydantic field type. "
    "If you are using a return type annotation that is not a valid Pydantic "
    "field (e.g. Union[Response, dict, None]) you can disable generating the "
    "response model from the type annotation with the path operation decorator "
    "parameter response_model=None. Read more: "
    "https://fastapi.tiangolo.com/tutorial/response-model/"
)


def create_model_field(
    name: str,
    type_: Any,
    default: Any | None = Undefined,
    field_info: FieldInfo | None = None,
    alias: str | None = None,
    mode: Literal["validation", "serialization"] = "validation",
) -> ModelField:
    if annotation_is_pydantic_v1(type_):
        raise PydanticV1NotSupportedError(
            "pydantic.v1 models are no longer supported by FastAPI."
            f" Please update the response model {type_!r}."
        )
    field_info = field_info or FieldInfo(annotation=type_, default=default, alias=alias)
    try:
        return v2.ModelField(mode=mode, name=name, field_info=field_info)
    except PydanticSchemaGenerationError:
        raise fastapi.exceptions.FastAPIError(
            _invalid_args_message.format(type_=type_)
        ) from None


def normalize_header_name(name: str) -> str:
    """
    Normalize a header name for case-insensitive matching, treating underscores
    as dashes, so a Pydantic field `x_token` (or alias `X-Token`) matches the
    `X-Token` HTTP header.
    """
    return name.strip().lower().replace("_", "-")


def create_response_headers_field(*, name: str, model: Any) -> ModelField:
    """
    Create the field used to validate response headers against a
    `response_headers_model` (a Pydantic model class).
    """
    if annotation_is_pydantic_v1(model):
        raise PydanticV1NotSupportedError(
            "pydantic.v1 models are no longer supported by FastAPI."
            f" Please update the response headers model {model!r}."
        )
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise fastapi.exceptions.FastAPIError(
            "response_headers_model must be a Pydantic model class, "
            f"got {model!r}."
        )
    return create_model_field(name=name, type_=model, mode="validation")


def _is_repeated_header_annotation(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    if origin in (list, tuple, set, frozenset):
        return True
    if origin is collections.abc.Sequence:
        return True
    if origin is Union or origin is types.UnionType:
        return any(
            _is_repeated_header_annotation(arg) for arg in get_args(annotation)
        )
    return False


def _get_header_field_key(field_name: str, field_info: FieldInfo) -> str:
    validation_alias = field_info.validation_alias
    if isinstance(validation_alias, str):
        return validation_alias
    if field_info.alias:
        return field_info.alias
    return field_name


def build_response_headers_data(
    model: type[BaseModel], raw_headers: Any
) -> dict[str, Any]:
    """
    Build the input dict used to validate a `response_headers_model` from the
    raw headers of the response about to be sent.

    Merging rules:

    * Header names are matched case-insensitively, `_` in field names matches
      `-` in header names.
    * Fields declared with a sequence type (e.g. `list[str]`) receive all the
      lines of the header, in order (repeated headers).
    * Scalar fields for headers other than `Set-Cookie` receive the combined
      `", "`-joined value when the header has multiple lines (RFC 9110).
    * `Set-Cookie` is never combined: a scalar field receives the last line,
      use a sequence field (e.g. `list[str]`) to receive every cookie line.
    """
    grouped: dict[str, list[str]] = {}
    for raw_name, raw_value in raw_headers:
        name = (
            raw_name.decode("latin-1") if isinstance(raw_name, bytes) else raw_name
        )
        value = (
            raw_value.decode("latin-1")
            if isinstance(raw_value, bytes)
            else raw_value
        )
        grouped.setdefault(name.lower(), []).append(value)
    data: dict[str, Any] = {}
    for field_name, field_info in model.model_fields.items():
        key = _get_header_field_key(field_name, field_info)
        normalized = normalize_header_name(key)
        values = grouped.get(normalized)
        if values is None:
            continue
        if _is_repeated_header_annotation(field_info.annotation):
            data[key] = values
        elif normalized == "set-cookie":
            data[key] = values[-1]
        elif len(values) > 1:
            data[key] = ", ".join(values)
        else:
            data[key] = values[0]
    return data


def validate_response_headers(
    *,
    field: ModelField,
    raw_headers: Any,
    endpoint_ctx: EndpointContext | None = None,
) -> None:
    """
    Validate the headers of a response against its `response_headers_model`
    right before it is sent, raising `ResponseValidationError` if they don't
    match the declared model.
    """
    model = field.field_info.annotation
    assert isinstance(model, type) and issubclass(model, BaseModel)
    data = build_response_headers_data(model, raw_headers)
    _, errors = field.validate(data, {}, loc=("response_headers",))
    if errors:
        ctx = endpoint_ctx or EndpointContext()
        raise ResponseValidationError(errors=errors, endpoint_ctx=ctx)


def generate_operation_id_for_path(
    *, name: str, path: str, method: str
) -> str:  # pragma: nocover
    warnings.warn(
        message="fastapi.utils.generate_operation_id_for_path() was deprecated, "
        "it is not used internally, and will be removed soon",
        category=FastAPIDeprecationWarning,
        stacklevel=2,
    )
    operation_id = f"{name}{path}"
    operation_id = re.sub(r"\W", "_", operation_id)
    operation_id = f"{operation_id}_{method.lower()}"
    return operation_id


def generate_unique_id(route: "APIRoute") -> str:
    operation_id = f"{route.name}{route.path_format}"
    operation_id = re.sub(r"\W", "_", operation_id)
    assert route.methods
    operation_id = f"{operation_id}_{list(route.methods)[0].lower()}"
    return operation_id


def deep_dict_update(main_dict: dict[Any, Any], update_dict: dict[Any, Any]) -> None:
    for key, value in update_dict.items():
        if (
            key in main_dict
            and isinstance(main_dict[key], dict)
            and isinstance(value, dict)
        ):
            deep_dict_update(main_dict[key], value)
        elif (
            key in main_dict
            and isinstance(main_dict[key], list)
            and isinstance(update_dict[key], list)
        ):
            main_dict[key] = main_dict[key] + update_dict[key]
        else:
            main_dict[key] = value


def get_value_or_default(
    first_item: DefaultPlaceholder | DefaultType,
    *extra_items: DefaultPlaceholder | DefaultType,
) -> DefaultPlaceholder | DefaultType:
    """
    Pass items or `DefaultPlaceholder`s by descending priority.

    The first one to _not_ be a `DefaultPlaceholder` will be returned.

    Otherwise, the first item (a `DefaultPlaceholder`) will be returned.
    """
    items = (first_item,) + extra_items
    for item in items:
        if not isinstance(item, DefaultPlaceholder):
            return item
    return first_item
