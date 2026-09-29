from fastapi import FastAPI, Query
from pydantic import BaseModel

app = FastAPI()


class RangeFilter(BaseModel):
    min: int = 0
    max: int = 100


class FilterParams(BaseModel):
    name: str = ""
    range: RangeFilter = RangeFilter()


@app.get("/items/")
async def read_items(filter: FilterParams = Query(style="deepObject")):
    return filter
