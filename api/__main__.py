"""`make run-api`: API дашборда только на localhost (решение заказчика 14.10.2026).

В контейнере на сервере (E9) API_HOST=0.0.0.0: порт открыт только во внутренней сети docker,
наружу — только сайт через Traefik.
"""

import logging
import os

import uvicorn

from api.app import create_app

HOST = os.environ.get("API_HOST", "127.0.0.1")
PORT = 8000


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx на INFO пишет полный адрес запроса — у FRED и Alpha Vantage в нём ключ API
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
