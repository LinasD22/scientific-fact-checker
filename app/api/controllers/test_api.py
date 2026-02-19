from typing import Annotated

from fastapi import Body, FastAPI, status
from fastapi.responses import JSONResponse

from app.bin import app



@app.get("/test")
def upsert_item(
    name: Annotated[str | None, Body()] = None,
    size: Annotated[int | None, Body()] = None,
):
    response = {"test": name, "size": size}
    return JSONResponse(status_code=status.HTTP_200_OK, content=response)