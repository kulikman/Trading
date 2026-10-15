"""`learn season` (SPEC §9, T20): обучение трёх моделей, принятие версии, θ и Келли, карантин.

1. События с признаками на T−1 (`feature_snapshot`, только не-shadow агенты) и итогами архива
   (`earnings_track`): p_beat — EPS ≥ консенсуса, p_up — движение > 0, move_ratio — |движение| >
   implied move.
2. Разбиение по времени: последние `holdout_fraction` — отложенная выборка.
3. Каждая модель — логистическая регрессия по `active_features` и калибровка Platt.
   Изотоническая калибровка (SPEC: при 300+ наблюдениях) — не реализована, пока данных меньше.
4. Модель обновляется, только если Brier на отложенной выборке лучше действующей; иначе в новой
   версии — параметры действующей. Версия принята, если улучшилась хоть одна модель. Отклонённая
   версия тоже сохраняется (с причиной) — её веса использует исследование 20% событий.
5. Правило 30: модель обучается от `min_segment_obs` наблюдений; θ и Келли — от 30 сделок.
6. θ и множитель Келли — рекомендация по paper-сделкам и теням (пороги в конфиге решает заказчик).
7. Вклад агента — насколько хуже Brier без его признаков; признаки, без которых лучше, — к
   отключению. Карантин — Brier прогноза p_up компании выше `models.quarantine.max_brier` на
   `models.quarantine.min_reports` и более отчётах.
Отчёт — `reports/season_<версия>.md`.
"""

import logging
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import AppConfig
from core.db import models as orm
from core.domain.types import CalibrationStatus, ModelName
from core.text import plural
from execution.paper import entry_step
from learning.fit import brier, fit_logistic, fit_platt, robust_scale
from models.features import stage_features
from models.logistic import ModelParams
from models.versions import MODEL_NAMES, PRIOR_VERSION, active_models

logger = logging.getLogger(__name__)

THETAS = (0.50, 0.55, 0.60, 0.65, 0.70)
KELLY_MULTIPLIERS = (0.125, 0.25, 0.5)  # варианты sizing.kelly_multiplier


@dataclass(frozen=True)
class Sample:
    event_id: int
    ticker: str
    report_date: date
    features: dict[str, float]
    labels: dict[ModelName, int]
    forecast_p_up: float | None


@dataclass
class ModelOutcome:
    model: ModelName
    observations: int
    params: ModelParams
    brier_new: float | None = None
    brier_old: float | None = None
    improved: bool = False
    reason: str = ""
    fitted: ModelParams | None = (
        None  # обученные веса, даже если не лучше: их пробует «исследование»
    )


@dataclass
class SeasonResult:
    version: str
    accepted: bool
    reason: str
    models: list[ModelOutcome] = field(default_factory=list)
    contributions: dict[str, float] = field(default_factory=dict)
    disable: list[str] = field(default_factory=list)
    theta: str = ""
    quarantine: dict[str, str] = field(default_factory=dict)
    samples: int = 0
    report: Path | None = None


def build_samples(session: Session, config: AppConfig) -> list[Sample]:
    """События с признаками T−1 и итогами архива, по дате отчёта."""
    rows = session.execute(
        select(orm.Event, orm.EarningsTrack)
        .join(
            orm.EarningsTrack,
            (orm.EarningsTrack.ticker == orm.Event.ticker)
            & (orm.EarningsTrack.report_date == orm.Event.report_date),
        )
        .where(orm.EarningsTrack.date_check.is_distinct_from("mismatch"))
        .order_by(orm.Event.report_date, orm.Event.id)
    ).all()
    out = []
    for event, track in rows:
        features = stage_features(session, event.id, "T-1", config.registry)
        if not features:
            continue
        labels: dict[ModelName, int] = {}
        if track.eps_actual is not None and track.eps_consensus is not None:
            labels["p_beat"] = int(track.eps_actual >= track.eps_consensus)
        if track.actual_move is not None:
            labels["p_up"] = int(track.actual_move > 0)
            implied = track.implied_move or features.get("options.implied_move")
            if implied:
                labels["move_ratio"] = int(abs(track.actual_move) > implied)
        if not labels:
            continue
        forecast = session.scalars(
            select(orm.Forecast.p_up)
            .where(orm.Forecast.event_id == event.id, orm.Forecast.stage == "T-1")
            .order_by(orm.Forecast.created_at.desc())
            .limit(1)
        ).first()
        out.append(Sample(event.id, event.ticker, event.report_date, features, labels, forecast))
    return out


def learn_season(session: Session, config: AppConfig, now: datetime) -> SeasonResult:
    """Обучить, решить о версии, записать model_version и карантин (отчёт — write_report)."""
    settings = config.thresholds.models
    samples = build_samples(session, config)
    current = active_models(session)
    version = _next_version(session)
    names = list(settings.active_features)
    outcomes = [_learn_model(m, samples, names, current.params[m], config) for m in MODEL_NAMES]
    improved = [o for o in outcomes if o.improved]
    accepted = bool(improved)
    reason = (
        "принята: Brier лучше у " + ", ".join(o.model for o in improved)
        if accepted
        else "отклонена: " + "; ".join(f"{o.model} — {o.reason}" for o in outcomes)
    )
    result = SeasonResult(
        version=version, accepted=accepted, reason=reason, models=outcomes, samples=len(samples)
    )
    result.contributions, result.disable = _contributions(samples, names, config)
    result.theta = _theta_kelly(session, config)
    result.quarantine = _quarantine(session, samples, config)
    if not any(o.brier_new is not None for o in outcomes):
        # Ни одна модель не обучалась — версии нет (иначе «исследование» шло бы на старых весах).
        result.reason = "мало данных — версия не создана: " + "; ".join(
            f"{o.model} — {o.reason}" for o in outcomes
        )
        return result
    for outcome in outcomes:
        # Отклонённая версия хранит новые веса — их пробуют 20% событий (исследование, SPEC §9).
        params = outcome.params if accepted else (outcome.fitted or outcome.params)
        metrics: dict[str, object] = {"n": outcome.observations}
        if outcome.brier_new is not None:
            metrics |= {"brier": outcome.brier_new, "brier_old": outcome.brier_old}
        if current.metrics.get(outcome.model, {}).get("base_rate") is not None:
            metrics["base_rate"] = current.metrics[outcome.model]["base_rate"]
        metrics["contributions"] = result.contributions
        session.add(
            orm.ModelVersion(
                model=outcome.model,
                version=version,
                params=params.model_dump(),
                metrics=metrics,
                trained_at=now,
                accepted=accepted,
                reason=f"{outcome.model}: {outcome.reason}. Версия {reason}",
            )
        )
    session.flush()
    logger.info("learn season", extra={"version": version, "accepted": accepted})
    return result


def _learn_model(
    model: ModelName,
    samples: Sequence[Sample],
    names: Sequence[str],
    current: ModelParams,
    config: AppConfig,
) -> ModelOutcome:
    settings = config.thresholds.models
    rows = [s for s in samples if model in s.labels]
    outcome = ModelOutcome(model=model, observations=len(rows), params=current)
    if len(rows) < settings.min_segment_obs:
        outcome.reason = f"мало наблюдений: {len(rows)} из {settings.min_segment_obs}"
        return outcome
    split = max(1, int(len(rows) * (1 - settings.holdout_fraction)))
    train, test = rows[:split], rows[split:] or rows[-1:]
    params = _fit(model, train, names, config)
    outcome.brier_new = brier(params, [s.features for s in test], [s.labels[model] for s in test])
    outcome.brier_old = brier(current, [s.features for s in test], [s.labels[model] for s in test])
    outcome.improved = outcome.brier_new < outcome.brier_old
    outcome.fitted = params
    outcome.params = params if outcome.improved else current
    outcome.reason = (
        f"Brier {outcome.brier_new:.4f} против {outcome.brier_old:.4f} "
        f"({'лучше' if outcome.improved else 'не лучше — остаётся действующая'})"
    )
    return outcome


def _fit(
    model: ModelName, train: Sequence[Sample], names: Sequence[str], config: AppConfig
) -> ModelParams:
    configured = {w.feature: w.scale for w in config.thresholds.models.p_up_feature_map.values()}
    scales = {
        n: configured.get(n) or robust_scale([s.features[n] for s in train if n in s.features])
        for n in names
    }
    rows, labels = [s.features for s in train], [s.labels[model] for s in train]
    return fit_platt(fit_logistic(rows, labels, names, scales), rows, labels)


def _contributions(
    samples: Sequence[Sample], names: Sequence[str], config: AppConfig
) -> tuple[dict[str, float], list[str]]:
    """Вклад агента (Brier без него − с ним, p_up) и признаки, без которых Brier лучше."""
    settings = config.thresholds.models
    rows = [s for s in samples if "p_up" in s.labels]
    if len(rows) < settings.min_segment_obs:
        return {}, []
    split = max(1, int(len(rows) * (1 - settings.holdout_fraction)))
    train, test = rows[:split], rows[split:] or rows[-1:]

    def holdout_brier(subset: Sequence[str]) -> float:
        params = _fit("p_up", train, subset, config)
        return brier(params, [s.features for s in test], [s.labels["p_up"] for s in test])

    full = holdout_brier(names)
    agents = sorted({n.split(".", 1)[0] for n in names})
    contributions = {
        a: round(holdout_brier([n for n in names if not n.startswith(f"{a}.")]) - full, 4)
        for a in agents
    }
    disable = [n for n in names if holdout_brier([m for m in names if m != n]) < full]
    return contributions, disable


def _theta_kelly(session: Session, config: AppConfig) -> str:
    """Рекомендация θ (максимум Sharpe отобранных сделок) и множителя Келли (максимум роста).

    Множитель — тот же, что `sizing.kelly_multiplier`: риск сделки = множитель · (p·b − (1−p)) / b,
    p — вероятность модели в шаге решения, b — средний выигрыш / средний проигрыш на риск сделок.
    """
    minimum = config.thresholds.models.min_segment_obs
    trades: list[tuple[float, float | None, float]] = []  # (уверенность, p, доходность на риск)
    capital = config.thresholds.capital.module_usd
    for card, decision in session.execute(
        select(orm.TradeCard, orm.Decision)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .where(
            orm.TradeCard.paper.is_(True),  # Real дублирует решение paper
            orm.TradeCard.state.in_(("CLOSED", "STOPPED")),
            orm.TradeCard.pnl_total.is_not(None),
        )
    ).all():
        step = entry_step(session, decision)  # одна сделка — один шаг (у режима B их два)
        risk = capital * (step.risk_fraction or 0.0) if step is not None else 0.0
        if step is not None and risk > 0 and step.confidence is not None:
            trades.append((step.confidence, step.probability, float(card.pnl_total or 0) / risk))
    for shadow, step in session.execute(
        select(orm.ShadowTrade, orm.DecisionStep)
        .join(orm.DecisionStep, orm.DecisionStep.id == orm.ShadowTrade.step_id)
        .where(orm.ShadowTrade.status == "closed", orm.ShadowTrade.return_on_risk.is_not(None))
    ).all():
        if step.confidence is not None and shadow.return_on_risk is not None:
            trades.append((step.confidence, step.probability, shadow.return_on_risk))
    count = f"по {len(trades)} {plural(len(trades), 'сделке', 'сделкам', 'сделкам')}"
    if len(trades) < minimum:
        return f"мало сделок для θ и Келли: {len(trades)} из {minimum} — пороги не меняются"
    best_theta, best_sharpe = None, float("-inf")
    for theta in THETAS:
        chosen = [r for c, _, r in trades if c >= theta]
        if len(chosen) >= minimum and statistics.pstdev(chosen) > 0:
            sharpe = statistics.fmean(chosen) / statistics.pstdev(chosen)
            if sharpe > best_sharpe:
                best_theta, best_sharpe = theta, sharpe
    theta_text = (
        f"θ = {best_theta:.2f} (Sharpe {best_sharpe:.2f})"
        if best_theta is not None
        else "θ — не хватает сделок выше порогов"
    )
    return f"{theta_text}; {_kelly_text(trades, best_theta or 0.0)} ({count}) — рекомендация"


def _kelly_text(trades: Sequence[tuple[float, float | None, float]], theta: float) -> str:
    """Множитель Келли с максимальным средним log-ростом на сделках выше θ с вероятностью модели."""
    chosen = [(p, r) for c, p, r in trades if c >= theta and p is not None]
    wins = [r for _, r in chosen if r > 0]
    losses = [-r for _, r in chosen if r < 0]
    if not wins or not losses:
        return "множитель Келли — нужны и выигрыши, и проигрыши с вероятностью модели"
    b = statistics.fmean(wins) / statistics.fmean(losses)

    def growth(multiplier: float) -> float:
        risks = [(max(multiplier * (p * b - (1 - p)) / b, 0.0), r) for p, r in chosen]
        return statistics.fmean(_log_growth(f * r) for f, r in risks)

    best = max(KELLY_MULTIPLIERS, key=growth)
    return f"множитель Келли = {best:g} (b = {b:.2f}, сделок с p: {len(chosen)})"


def _quarantine(session: Session, samples: Sequence[Sample], config: AppConfig) -> dict[str, str]:
    """Brier прогноза p_up компании выше порога на достаточном числе отчётов — карантин."""
    limits = config.thresholds.models.quarantine
    by_ticker: dict[str, list[tuple[float, int]]] = {}
    for s in samples:
        if s.forecast_p_up is not None and "p_up" in s.labels:
            by_ticker.setdefault(s.ticker, []).append((s.forecast_p_up, s.labels["p_up"]))
    changes = {}
    for ticker, pairs in by_ticker.items():
        if len(pairs) < limits.min_reports:
            continue
        score = statistics.fmean((p - y) ** 2 for p, y in pairs)
        company = session.get(orm.Company, ticker)
        if company is None:
            continue
        status: CalibrationStatus = "quarantine" if score > limits.max_brier else "active"
        if company.calibration_status != status:
            company.calibration_status = status
            word = "в карантин" if status == "quarantine" else "из карантина"
            reports = plural(len(pairs), "отчёте", "отчётах", "отчётах")
            changes[ticker] = f"{word} (Brier {score:.3f} на {len(pairs)} {reports})"
    session.flush()
    return changes


def _next_version(session: Session) -> str:
    count = session.scalar(select(func.count(func.distinct(orm.ModelVersion.version)))) or 0
    return f"0.{count + 1}.0" if count else PRIOR_VERSION


def _log_growth(x: float) -> float:
    return math.log(max(1.0 + x, 1e-9))


def write_report(result: SeasonResult, report_dir: Path) -> Path:
    """Отчёт сезона reports/season_<версия>.md — после commit, чтобы не было отчёта без версии."""
    samples = result.samples
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"season_{result.version}.md"
    lines = [
        f"# Сезон — версия моделей {result.version}",
        "",
        f"Дата: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Событий с признаками и итогами: {samples}.",
        "",
        f"**Решение:** {result.reason}.",
        "",
        "| Модель | Наблюдений | Brier новой | Brier действующей | Итог |",
        "|---|---|---|---|---|",
    ]
    for o in result.models:
        new = "—" if o.brier_new is None else f"{o.brier_new:.4f}"
        old = "—" if o.brier_old is None else f"{o.brier_old:.4f}"
        lines.append(f"| {o.model} | {o.observations} | {new} | {old} | {o.reason} |")
    lines += [
        "",
        "## θ и множитель Келли",
        "",
        result.theta,
        "",
        "## Вклад агентов (Brier без агента − с ним, p_up)",
        "",
    ]
    lines += [f"- {a}: {d:+.4f}" for a, d in sorted(result.contributions.items())] or [
        "- мало данных"
    ]
    lines += ["", "## Признаки к отключению", ""]
    lines += [f"- {n}" for n in result.disable] or ["- нет"]
    lines += ["", "## Карантин", ""]
    lines += [f"- {t}: {s}" for t, s in sorted(result.quarantine.items())] or ["- без изменений"]
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:  # pragma: no cover
    """`make learn-season`: обучение сезона на базе системы; отчёт в reports/."""
    from core.config import load_config
    from core.db.session import create_db_engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with Session(create_db_engine()) as session, session.begin():
        result = learn_season(session, load_config(), datetime.now(UTC))
    result.report = write_report(result, Path("reports"))
    logger.info("Версия %s: %s. Отчёт: %s", result.version, result.reason, result.report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
