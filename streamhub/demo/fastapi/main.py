import os
from typing import Optional

import click
import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel

# Streamhub strips "/<app_id>" before forwarding, and sets STREAMHUB_BASE_PATH so the docs use the right URLs.
app = FastAPI(title="This is a Hello World! API",
              version="1.0",
              description="This is the API description.",
              root_path=os.environ.get("STREAMHUB_BASE_PATH", ""))


class Item(BaseModel):
    name: str
    price: float
    is_offer: Optional[bool] = None


@app.get("/")
def read_root(request: Request):
    return {"message": "Hello World", "root_path": request.scope.get("root_path")}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_name": item.name, "item_id": item_id}


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    return {"deleted": item_id}


# -- SUB API --
subapi = FastAPI()


@subapi.get("/sub")
def read_sub():
    return {"message": "Hello World from sub API"}


app.mount("/subapi", subapi)


@click.command()
@click.option('--port', default=5000, help='Server port', type=int)
@click.option('--app_id', default='', help='Streamhub app id')
def run(port, app_id):
    uvicorn.run(app, host=os.environ.get("STREAMHUB_HOST", "127.0.0.1"), port=port, access_log=False)


if __name__ == "__main__":
    run()
