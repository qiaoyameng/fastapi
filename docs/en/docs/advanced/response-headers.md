# Response Headers { #response-headers }

## Use a `Response` parameter { #use-a-response-parameter }

You can declare a parameter of type `Response` in your *path operation function* (as you can do for cookies).

And then you can set headers in that *temporary* response object.

{* ../../docs_src/response_headers/tutorial002_py310.py hl[1, 7:8] *}

And then you can return any object you need, as you normally would (a `dict`, a database model, etc).

And if you declared a `response_model`, it will still be used to filter and convert the object you returned.

**FastAPI** will use that *temporary* response to extract the headers (also cookies and status code), and will put them in the final response that contains the value you returned, filtered by any `response_model`.

You can also declare the `Response` parameter in dependencies, and set headers (and cookies) in them.

## Return a `Response` directly { #return-a-response-directly }

You can also add headers when you return a `Response` directly.

Create a response as described in [Return a Response Directly](response-directly.md) and pass the headers as an additional parameter:

{* ../../docs_src/response_headers/tutorial001_py310.py hl[10:12] *}

/// note | Technical Details

You could also use `from starlette.responses import Response` or `from starlette.responses import JSONResponse`.

**FastAPI** provides the same `starlette.responses` as `fastapi.responses` just as a convenience for you, the developer. But most of the available responses come directly from Starlette.

And as the `Response` can be used frequently to set headers and cookies, **FastAPI** also provides it at `fastapi.Response`.

///

## Custom Headers { #custom-headers }

Keep in mind that custom proprietary headers can be added [using the `X-` prefix](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers).

But if you have custom headers that you want a client in a browser to be able to see, you need to add them to your CORS configurations (read more in [CORS (Cross-Origin Resource Sharing)](../tutorial/cors.md)), using the parameter `expose_headers` documented in [Starlette's CORS docs](https://starlette.dev/middleware/#corsmiddleware).

## Declare and validate response headers with `response_headers_model` { #response-headers-model }

You can declare the response headers of a *path operation* with a Pydantic model, using the parameter `response_headers_model`:

```Python
from fastapi import FastAPI, Response
from pydantic import BaseModel, Field


class ItemHeaders(BaseModel):
    x_token: str = Field(alias="X-Token")
    x_count: int = Field(alias="X-Count")
    x_languages: list[str] = Field(default=[], alias="X-Languages")


app = FastAPI()


@app.get("/items/", response_headers_model=ItemHeaders)
def read_items(response: Response):
    response.headers["X-Token"] = "secret-token"
    response.headers["X-Count"] = "42"
    return [{"name": "Empanada"}, {"name": "Arepa"}]
```

Each field of the model declares a response header:

* The field name (or its alias) is the header name, matched case-insensitively. `_` in field names matches `-` in header names, so a field `x_token` matches the `X-Token` header.
* Fields without a default value are **required** headers.
* The header values are **validated and converted** with Pydantic, e.g. a field declared as `int` will parse the header value as an integer (and fail if it is not a valid integer).
* Fields declared with a sequence type (e.g. `list[str]`) receive **repeated** header lines, in order.

The final headers are validated right before the response is sent. If validation fails (e.g. a required header is missing or a value cannot be converted), a `ResponseValidationError` is raised, resulting in a 500 error, as it means your code didn't comply with the contract declared for the clients.

The validation applies to the final response, including:

* Responses without a body, like `HEAD` requests and `204 No Content` responses.
* `Response` objects returned directly by the *path operation* (see below).
* Streaming responses (the headers are validated before the streaming starts).

The same declaration is used to document the response headers in the generated OpenAPI (and the UI at `/docs`).

### `Set-Cookie` headers { #response-headers-model-set-cookie }

`Set-Cookie` is special: it can (and normally should) appear multiple times in a response, once per cookie, and its lines must never be combined into a single comma-separated value like other headers can.

Because of that, `Set-Cookie` is never merged with other headers nor combined. Declare it with a sequence type (e.g. `list[str]`) to receive every cookie line:

```Python
class CookieHeaders(BaseModel):
    set_cookie: list[str] = Field(alias="Set-Cookie")
```

### Headers from dependencies and responses returned directly { #response-headers-model-merging }

When a *path operation* returns a `Response` directly, the headers written by dependencies (or by the *path operation* itself) to the injected `Response` parameter are merged into the returned response with these rules:

* `Set-Cookie` headers are always appended, keeping each cookie on its own line.
* Any other header is only added if the returned response doesn't already have a header with that name: headers set directly on the returned `Response` take precedence over the ones written to the injected `Response`.

The merged headers are then validated against the `response_headers_model` before the response is sent, the same way as for any other response.
