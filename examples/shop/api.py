from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .services import create_order, preview_order

app = FastAPI()


class OrderInput(BaseModel):
    quantity: int


@app.post("/orders", status_code=201)
def create_order_route(order: OrderInput) -> dict:
    try:
        return create_order(order.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/orders/preview")
def preview_order_route(order: OrderInput) -> dict:
    try:
        return preview_order(order.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
