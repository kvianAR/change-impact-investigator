def validate_order(quantity: int) -> bool:
    """Accept order quantities from 1 through 100."""
    return 1 <= quantity <= 100
