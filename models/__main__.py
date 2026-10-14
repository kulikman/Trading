"""`make models-init`: стартовая версия моделей (до первого `learn season`, SPEC §9)."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.config import load_config
from core.db.session import create_db_engine
from core.session_guard import to_et
from models.versions import active_models, init_prior

logger = logging.getLogger("models")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    now = datetime.now(UTC)
    with Session(create_db_engine()) as session, session.begin():
        created = init_prior(
            session, load_config().thresholds.models, today=to_et(now).date(), now=now
        )
        version = active_models(session).version
    logger.info(
        "Стартовая версия моделей %s %s", version, "создана" if created else "уже есть — не меняю"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
