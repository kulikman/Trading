"""`make promote ARGS="mode_c"`: попытка поднять плагин на одну ступень (SPEC §7).

Сначала синхронизирует реестр с БД (новые плагины появляются со стадией из registry.yaml),
затем решает по метрикам отложенной выборки и пишет попытку в журнал plugin_stage_change.
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.config import load_config
from core.db.session import create_db_engine, database_url
from core.registry.promote import NoEvidence, promote
from core.registry.state import sync_plugins

logger = logging.getLogger("core.registry")


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Подъём плагина на одну ступень")
    parser.add_argument("command", choices=["promote"])
    parser.add_argument("plugin", help="id плагина из registry.yaml")
    args = parser.parse_args(argv)
    config = load_config()
    entry = next((p for p in config.registry.plugins if p.id == args.plugin), None)
    if entry is None:
        parser.error(f"{args.plugin}: нет в registry.yaml")
    with Session(create_db_engine(database_url())) as session, session.begin():
        sync_plugins(session, config.registry)
        result = promote(
            session,
            entry.id,
            entry.version,
            source=NoEvidence(),  # TODO(T15/T20): метрики моделей и сезона
            lifecycle=config.thresholds.lifecycle,
            now=datetime.now(UTC),
        )
    verdict = f"→ {result.to_stage}" if result.accepted else "отказ"
    logger.info(
        "%s %s: %s %s (%s)",
        result.plugin_id,
        result.version,
        result.from_stage,
        verdict,
        result.reason,
    )
    return 0 if result.accepted else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
