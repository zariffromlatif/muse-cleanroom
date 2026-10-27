"""Tiny order service used by Cleanroom benchmark case 02."""


def process_order(amount: int) -> dict:
    if amount <= 0:
        raise ValueError(f"order amount must be positive, got {amount}")
    return {"status": "ok", "charged": amount}


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(process_order(n))
