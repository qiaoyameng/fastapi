from typing import Annotated, Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class RangeFilter(BaseModel):
    min: int = Field(0, ge=0)
    max: int = Field(100, le=100)


class FilterParams(BaseModel):
    name: str = "all"
    order_by: Literal["created_at", "updated_at"] = Field(
        "created_at", alias="orderBy"
    )
    range: RangeFilter = Field(default_factory=RangeFilter)


@app.get("/items/")
async def read_items(filter: Annotated[FilterParams, Query(style="deepObject")]):
    return filter
