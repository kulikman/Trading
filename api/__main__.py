"""`make run-api`: API дашборда только на localhost (решение заказчика 14.10.2026)."""

import logging

import uvicorn

from api.app import create_app

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
