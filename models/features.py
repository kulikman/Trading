"""Признаки события для прогноза: «агент.признак» с последней стадии не позже текущей.

Агенты пишут признаки на своих стадиях (Сектор — T−14, Досье — T−10, Опционы — T−7 …).
Прогноз на T−3 видит свежие опционы T−3 и при этом сектор с T−14. Признаки shadow-агентов
и выключенных агентов в прогноз не попадают (решение их не видит, T13).
"""

from sqlalchemy.orm import Session

from core.config.registry import Registry
from core.domain.types import FeatureStage
from core.registry.agent_jobs import STAGES
from core.registry.state import decision_features


def stage_features(
    session: Session, event_id: int, stage: FeatureStage, registry: Registry
) -> dict[str, float]:
    """Плоский словарь «агент.признак» → значение; более поздняя стадия перекрывает раннюю."""
    flat: dict[str, float] = {}
    for current in STAGES[: STAGES.index(stage) + 1]:
        for agent_id, features in decision_features(session, event_id, current, registry).items():
            for name, value in features.items():
                flat[f"{agent_id}.{name}"] = float(value)
    return flat
