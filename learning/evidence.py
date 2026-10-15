"""Метрики для `promote` (SPEC §7, E10-1): из закрытых сделок и отчёта сезона.

Стратегия: Sharpe по сделкам (средняя / стандартное отклонение доходности на риск сделки).
- в shadow — по теневым сделкам стратегии (подъём в paper);
- в paper и выше — по закрытым paper-сделкам (подъём в live_small, то есть в Real).
Базовый уровень — 0 (не торговать); стратегия с Sharpe не выше нуля не поднимается. Наблюдения —
число сделок; правило — lifecycle.promote_min_obs (30). Все сделки — после решения, вне выборки,
на которой что-либо подбиралось, поэтому отдельной отложенной выборки нет.
Агент: Brier p_up без его признаков (базовый) и с ними — из последнего обучения сезона (T20).
"""

import statistics
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.plugin import Plugin
from core.registry.promote import PromotionEvidence
from execution.paper import entry_step

CLOSED_STATES = ("CLOSED", "STOPPED")


class DbEvidence:
    """Источник метрик для promote по базе системы."""

    def __init__(self, session: Session, thresholds: Thresholds) -> None:
        self._session = session
        self._thresholds = thresholds

    def evidence(self, plugin: Plugin) -> PromotionEvidence:
        if plugin.kind == "agent":
            return self._agent(plugin.id)
        returns = self._shadow(plugin.id) if plugin.stage == "shadow" else self._paper(plugin.id)
        return PromotionEvidence("sharpe", len(returns), 0.0, _sharpe(returns))

    def _paper(self, strategy_id: str) -> list[float]:
        """Доходность на риск закрытых paper-сделок стратегии."""
        capital = self._thresholds.capital.module_usd
        out: list[float] = []
        for card, decision in self._session.execute(
            select(orm.TradeCard, orm.Decision)
            .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
            .where(
                orm.Decision.strategy_id == strategy_id,
                orm.TradeCard.paper.is_(True),
                orm.TradeCard.state.in_(CLOSED_STATES),
                orm.TradeCard.pnl_total.is_not(None),
            )
        ).all():
            step = entry_step(self._session, decision)
            risk = capital * (step.risk_fraction or 0.0) if step is not None else 0.0
            if risk > 0:
                out.append(float(card.pnl_total or 0) / risk)
        return out

    def _shadow(self, strategy_id: str) -> list[float]:
        rows = self._session.scalars(
            select(orm.ShadowTrade.return_on_risk).where(
                orm.ShadowTrade.strategy_id == strategy_id,
                orm.ShadowTrade.status == "closed",
                orm.ShadowTrade.return_on_risk.is_not(None),
            )
        ).all()
        return [float(r) for r in rows if r is not None]

    def _agent(self, agent_id: str) -> PromotionEvidence:
        """Brier p_up с признаками агента (кандидат) и без них (базовый) из отчёта сезона."""
        latest = self._session.scalars(
            select(orm.ModelVersion)
            .where(orm.ModelVersion.model == "p_up")
            .order_by(orm.ModelVersion.trained_at.desc(), orm.ModelVersion.id.desc())
        ).all()
        for row in latest:
            metrics = row.metrics or {}
            contributions = metrics.get("contributions") or {}
            brier, n = metrics.get("brier"), metrics.get("n")
            if agent_id in contributions and brier is not None and n is not None:
                without = float(brier) + float(contributions[agent_id])
                return PromotionEvidence("brier", int(n), without, float(brier))
        return PromotionEvidence("brier", 0, None, None)


def _sharpe(returns: Sequence[float]) -> float | None:
    if len(returns) < 2 or statistics.pstdev(returns) == 0:
        return None
    return statistics.fmean(returns) / statistics.pstdev(returns)
