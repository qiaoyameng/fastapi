# Query Parameters with deepObject { #query-parameters-with-deepobject }

If you want to receive a **nested object** from the **query parameters**, you can use the OpenAPI **`deepObject`** style.

With `deepObject`, a client can send query parameters using **bracket keys**, like:

```http
https://example.com/items/?filter[name]=a&filter[range][min]=3
```

And **FastAPI** will give you a typed **Pydantic model** with the nested data.

/// note

This is an opt-in feature: query parameters are handled as usual (OpenAPI `"form"` style) unless you explicitly set `style="deepObject"`.

///

## Declare a `deepObject` Query Parameter { #declare-a-deepobject-query-parameter }

Declare the nested data in a **Pydantic model** (including other nested models), and set `style="deepObject"` in `Query()`:

{* ../../docs_src/query_params_deep_object/tutorial001_an_py310.py hl[9:19,23] *}

**FastAPI** will **expand** the bracket keys of the `filter` query parameter into a nested object and **validate** it with the Pydantic model, so you get the model with all its data types, validations, aliases, and default values.

For example, with the request:

```http
https://example.com/items/?filter[name]=a&filter[range][min]=3
```

You would get:

```Python
filter = FilterParams(
    name="a",
    order_by="created_at",
    range=RangeFilter(min=3, max=100),
)
```

Model **aliases** are used for the bracket keys, so `filter[orderBy]=updated_at` would set the `order_by` field. **Default values** are used for any key that is not sent. And **validation errors** point to the exact key, for example `query -> filter -> range -> min`.

## Limitations { #limitations }

Only **objects** with **scalar leaves** are supported:

* **Arrays** are not supported: keys with empty segments like `filter[tags][]=a` or repeated keys like `filter[name]=a&filter[name]=b` are rejected with a `422` error.
* **Conflicting paths** are not supported: mixing a scalar and an object for the same key, like `filter=a&filter[name]=b`, is rejected with a `422` error.

## Check the Docs { #check-the-docs }

The generated OpenAPI (and the docs UI at `/docs`) declares the parameter with `style: deepObject` and `explode: true`:

```json
{
    "name": "filter",
    "in": "query",
    "required": true,
    "schema": {"$ref": "#/components/schemas/FilterParams"},
    "style": "deepObject",
    "explode": true
}
```
