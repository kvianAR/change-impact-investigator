from .validators import validate_order


def create_order(quantity: int) -> dict:
    if not validate_order(quantity):
        raise ValueError("Quantity must be between 1 and 100")
    return {"quantity": quantity, "status": "created"}


def preview_order(quantity: int) -> dict:
    if not validate_order(quantity):
        raise ValueError("Quantity must be between 1 and 100")
    return {"quantity": quantity, "total": quantity * 10}
