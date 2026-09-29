# Query Parameter Models { #query-parameter-models }

If you have a group of **query parameters** that are related, you can create a **Pydantic model** to declare them.

This would allow you to **re-use the model** in **multiple places** and also to declare validations and metadata for all the parameters at once. 😎

/// note

This is supported since FastAPI version `0.115.0`. 🤓

///

## Query Parameters with a Pydantic Model { #query-parameters-with-a-pydantic-model }

Declare the **query parameters** that you need in a **Pydantic model**, and then declare the parameter as `Query`:

{* ../../docs_src/query_param_models/tutorial001_an_py310.py hl[9:13,17] *}

**FastAPI** will **extract** the data for **each field** from the **query parameters** in the request and give you the Pydantic model you defined.

## Check the Docs { #check-the-docs }

You can see the query parameters in the docs UI at `/docs`:

<div class="screenshot">
<img src="/img/tutorial/query-param-models/image01.png">
</div>

## Forbid Extra Query Parameters { #forbid-extra-query-parameters }

In some special use cases (probably not very common), you might want to **restrict** the query parameters that you want to receive.

You can use Pydantic's model configuration to `forbid` any `extra` fields:

{* ../../docs_src/query_param_models/tutorial002_an_py310.py hl[10] *}

If a client tries to send some **extra** data in the **query parameters**, they will receive an **error** response.

For example, if the client tries to send a `tool` query parameter with a value of `plumbus`, like:

```http
https://example.com/items/?limit=10&tool=plumbus
```

They will receive an **error** response telling them that the query parameter `tool` is not allowed:

```json
{
    "detail": [
        {
            "type": "extra_forbidden",
            "loc": ["query", "tool"],
            "msg": "Extra inputs are not permitted",
            "input": "plumbus"
        }
    ]
}
```

## Nested Query Parameters with `deepObject` { #nested-query-parameters-with-deepobject }

If your query parameter model has **nested models**, you can declare it with `Query(style="deepObject")` to read the nested data from **bracket query keys**, following the OpenAPI `deepObject` serialization style.

{* ../../docs_src/query_param_models/tutorial003_an_py310.py hl[15] *}

With this, a request like:

```http
https://example.com/items/?filter[name]=a&filter[range][min]=3
```

is parsed as the nested object `{"name": "a", "range": {"min": 3}}` and validated against the `FilterParams` model, so you get the typed model directly, with all the existing validations, aliases, and defaults applied.

The generated OpenAPI will declare the parameter with `style: deepObject` and `explode: true`.

/// note

Only nested **objects** with **scalar** leaf values are supported. Arrays (e.g. `filter[tags][]=a`) and conflicting scalar/object paths (e.g. `filter[name]=a` together with `filter[name][sub]=b`) are rejected with a `422` error.

Without `style="deepObject"`, query parameters keep the default behavior, and bracket keys are treated as plain parameter names.

///

## Summary { #summary }

You can use **Pydantic models** to declare **query parameters** in **FastAPI**. 😎

/// tip

Spoiler alert: you can also use Pydantic models to declare cookies and headers, but you will read about that later in the tutorial. 🤫

///
