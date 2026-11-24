"""Read existing fills and persist sampled exit research without a second ledger."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from database.nifty_replay_storage import ReplayStorage
from services.nifty_algo.ledger_analytics import fill_facts
from services.nifty_algo.models import Instrument, Quote


class ResearchAnalyticsStore(ReplayStorage):
    def execution_observations(self, user_id, floor, now):
        """SELECT-only capture; unlike orders(), this never expires an intent."""
        from database.nifty_algo_db import NiftyOrder, NiftyPosition, NiftyProtection, _instant

        observations = []
        with self.sessions() as db:
            fills = db.scalars(
                select(NiftyOrder)
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.status == "FILLED",
                    NiftyOrder.resolved_at >= floor,
                    NiftyOrder.resolved_at <= now,
                )
                .order_by(NiftyOrder.resolved_at.desc(), NiftyOrder.order_id)
                .limit(4)
            )
            for row in fills:
                if not row.payload.get("configuration_id"):
                    continue
                observations.append(
                    {
                        "kind": "LEDGER",
                        "source": "NATIVE_FEED",
                        "source_time": _instant(row.resolved_at),
                        "available_at": now.isoformat(),
                        "payload": {
                            "mode": "PAPER",
                            "event": "ENTRY_FILL" if row.side == "BUY" else "EXIT_FILL",
                            "token": row.token,
                            "entry_order_id": row.order_id
                            if row.side == "BUY"
                            else row.payload["entry_order_id"],
                            "order_id": row.order_id,
                            "quantity": row.quantity,
                            "price": str(row.price),
                            "fees": str(row.fees),
                            "reason": row.payload.get("exit_reason"),
                            "quote": row.payload.get("fill_observation"),
                            "selector_policy": (
                                (row.payload.get("sizing_plan") or {}).get("ranking") or [{}]
                            )[0].get("policy"),
                            "configuration_id": row.payload["configuration_id"],
                        },
                    }
                )
            positions = db.execute(
                select(NiftyPosition, NiftyProtection)
                .join(
                    NiftyProtection,
                    (NiftyProtection.user_id == user_id)
                    & (NiftyProtection.token == NiftyPosition.token),
                )
                .where(NiftyPosition.user_id == user_id)
                .limit(1)
            ).all()
            for row, protection in positions:
                p = protection.payload
                at = (
                    datetime.fromisoformat(p["last_source_time"])
                    if p.get("last_source_time")
                    else None
                )
                if at is None or not floor <= at <= now:
                    continue
                observations.append(
                    {
                        "kind": "LEDGER",
                        "source": "NATIVE_FEED",
                        "source_time": at.isoformat(),
                        "available_at": now.isoformat(),
                        "payload": {
                            "mode": "PAPER",
                            "event": "PROTECTION",
                            "token": row.token,
                            "entry_order_id": row.entry_order_id,
                            "quantity": row.quantity,
                            "stop_price": p["stop_price"],
                            "profit_floor_stop": p.get("profit_floor_stop"),
                            "profit_lock_active": p.get("profit_lock_active", False),
                            "reason": p.get("exit_reason"),
                            "configuration_id": p["configuration_id"],
                        },
                    }
                )
        return observations

    def comparative_analytics(self, user_id, start, end, *, side=None, reason=None):
        from sqlalchemy import and_, func
        from sqlalchemy.orm import aliased

        from database.nifty_algo_db import (
            NiftyExecutionResearch,
            NiftyOrder,
            NiftyResearchExperiment,
            NiftyShadowPosition,
            NiftyTrade,
            _instant,
        )
        from services.nifty_algo.analytics import performance
        from services.nifty_algo.execution_quality import fill_quality, summarize_quality
        from services.nifty_algo.ledger_analytics import AnalyticsDataError

        if side not in (None, "CE", "PE") or (
            reason is not None and (not isinstance(reason, str) or not 1 <= len(reason) <= 64)
        ):
            raise ValueError("Invalid comparison filters")
        authoritative = self.analytics_snapshot(user_id, start, end, limit=1)
        entry, exit_order = aliased(NiftyOrder), aliased(NiftyOrder)
        with self.sessions() as db:
            rows = db.execute(
                select(NiftyTrade, entry, exit_order)
                .join(
                    entry,
                    and_(entry.user_id == user_id, entry.order_id == NiftyTrade.entry_order_id),
                )
                .join(
                    exit_order,
                    and_(
                        exit_order.user_id == user_id,
                        exit_order.order_id == NiftyTrade.exit_order_id,
                    ),
                )
                .where(
                    NiftyTrade.user_id == user_id,
                    NiftyTrade.id <= authoritative["watermark"],
                    NiftyTrade.closed_at >= start,
                    NiftyTrade.closed_at < end,
                )
                .order_by(NiftyTrade.closed_at, NiftyTrade.id)
                .limit(5001)
            ).all()
            if len(rows) > 5000:
                raise AnalyticsDataError("Comparison exceeds 5000 fills")
            paper, entries, exits, protections, details = [], {}, [], {}, []
            unfiltered_net = Decimal(0)
            for trade, buy, sell in rows:
                journal, detail = fill_facts(trade, buy, sell)
                unfiltered_net += Decimal(journal["net"])
                if (side and journal["instrument"]["kind"] != side) or (
                    reason and trade.reason != reason
                ):
                    continue
                paper.append(journal)
                entry_quality, exit_quality = fill_quality(buy), fill_quality(sell)
                entries[buy.order_id] = entry_quality
                exits.append(exit_quality)
                protection = sell.payload.get("protection") or {}
                protections[buy.order_id] = protection
                if len(details) < 100:
                    details.append(
                        {**detail, "entry_quality": entry_quality, "exit_quality": exit_quality}
                    )
            if unfiltered_net != Decimal(authoritative["metrics"]["total_net"]):
                raise AnalyticsDataError("Comparison does not reconcile with authoritative fills")
            shadows = list(
                db.scalars(
                    select(NiftyShadowPosition)
                    .where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.closed_at >= start,
                        NiftyShadowPosition.closed_at < end,
                    )
                    .order_by(NiftyShadowPosition.closed_at, NiftyShadowPosition.id)
                    .limit(5001)
                )
            )
            if len(shadows) > 5000:
                raise AnalyticsDataError("Comparison exceeds 5000 shadow rows")
            independent, mirrors, unavailable = [], [], 0
            for row in shadows:
                if (side and row.instrument["kind"] != side) or (
                    reason and row.exit_reason != reason
                ):
                    continue
                if not row.additive:
                    mirrors.append(
                        {
                            "id": row.id,
                            "net": str(row.net) if row.net is not None else None,
                            "primary_entry_order_id": row.primary_entry_order_id,
                            "additive": False,
                        }
                    )
                    continue
                if row.net is None or row.gross is None:
                    unavailable += 1
                    continue
                fees = row.entry_fees + row.exit_fees if row.exit_fees is not None else None
                if fees is None or row.gross - fees != row.net:
                    raise AnalyticsDataError("Shadow costs do not reconcile")
                independent.append(
                    {
                        "trade_id": str(row.id),
                        "fill_id": str(row.id),
                        "instrument": row.instrument,
                        "quantity": row.quantity,
                        "opened": _instant(row.opened_at),
                        "closed": _instant(row.closed_at),
                        "gross": str(row.gross),
                        "charges": str(fees),
                        "net": str(row.net),
                        "planned_risk": (row.protection.get("sizing_plan") or {}).get(
                            "planned_loss"
                        ),
                        "exit_reason": row.exit_reason,
                    }
                )
            shadow_prior = db.scalar(
                select(func.sum(NiftyShadowPosition.net)).where(
                    NiftyShadowPosition.user_id == user_id,
                    NiftyShadowPosition.additive == 1,
                    NiftyShadowPosition.closed_at < start,
                )
            ) or Decimal(0)
            experiments = db.execute(
                select(NiftyExecutionResearch, NiftyResearchExperiment)
                .join(
                    NiftyResearchExperiment,
                    and_(
                        NiftyResearchExperiment.user_id == user_id,
                        NiftyResearchExperiment.id == NiftyExecutionResearch.experiment_id,
                    ),
                )
                .where(
                    NiftyExecutionResearch.user_id == user_id,
                    NiftyExecutionResearch.status == "COMPLETE",
                )
                .order_by(NiftyExecutionResearch.updated_at.desc())
                .limit(20)
            ).all()
            comparisons = []
            for result, definition in experiments:
                splits = definition.snapshot["splits"]
                included = all(
                    start <= datetime.fromisoformat(s["start"])
                    and datetime.fromisoformat(s["end"]) <= end
                    for s in splits
                )
                if included:
                    from services.nifty_algo.replay_lab import canonical_result

                    if canonical_result(result.payload) != result.sha256:
                        raise AnalyticsDataError("Research comparison integrity failed")
                    comparisons.append(
                        {
                            "experiment_id": result.experiment_id,
                            "sha256": result.sha256,
                            "result": {
                                **{k: v for k, v in result.payload.items() if k != "variants"},
                                "variants": [
                                    {
                                        **variant,
                                        "splits": [
                                            {
                                                k: v
                                                for k, v in split.items()
                                                if k not in ("trades", "rejections")
                                            }
                                            for split in variant["splits"]
                                        ],
                                    }
                                    for variant in result.payload.get("variants", [])
                                ],
                            },
                            "mode": "RESEARCH",
                            "additive": False,
                        }
                    )
        from services.nifty_algo.config import StrategyConfig

        seed = StrategyConfig().virtual_capital
        return {
            "period": authoritative["period"],
            "filters": {"side": side, "reason": reason},
            "paper": {
                "mode": "PAPER",
                "metrics": performance(paper, authoritative["opening_realized_equity"]),
                "details": details,
                "details_truncated": len(paper) > 100,
                "quality": summarize_quality(
                    list(entries.values()), exits, list(protections.values())
                ),
            },
            "independent_shadow": {
                "mode": "HYPOTHETICAL_SHADOW",
                "metrics": performance(independent, seed + shadow_prior)
                if seed + shadow_prior > 0
                else None,
                "status": "AVAILABLE" if seed + shadow_prior > 0 else "DEPLETED_LEDGER",
                "unavailable_outcomes": unavailable,
            },
            "mirrors": {"additive": False, "items": mirrors[:100], "total": len(mirrors)},
            "replay_comparisons": comparisons,
            "live": {"status": "UNAVAILABLE_LIVE_DISABLED"},
            "combined_total": None,
            "active_settings_changed": False,
        }

    def shadow_selection(self, user_id, decision_id, configuration_id):
        from database.nifty_algo_db import NiftyShadowPosition, _instant

        with self.sessions() as db:
            row = db.scalar(
                select(NiftyShadowPosition)
                .where(
                    NiftyShadowPosition.user_id == user_id,
                    NiftyShadowPosition.kind == "INDEPENDENT",
                    NiftyShadowPosition.decision_id == decision_id,
                    NiftyShadowPosition.protection["configuration_id"].as_string()
                    == configuration_id,
                )
                .order_by(NiftyShadowPosition.id.desc())
                .limit(1)
            )
            if row is None:
                return None
            sizing = row.protection.get("sizing_plan") or {}
            return {
                "evaluated_at": _instant(row.opened_at),
                "policy": (sizing.get("ranking") or [{}])[0].get("policy", "UNAVAILABLE"),
                "ranking": sizing.get("ranking", []),
                "rejections": sizing.get("rejections", []),
            }

    def save_research_inspection(self, user_id, experiment_id, now):
        from database.nifty_algo_db import (
            NiftyResearchExperiment,
            NiftyResearchResult,
            StateConflict,
        )
        from services.nifty_algo.replay_lab import canonical_result, inspect_experiment

        result = inspect_experiment(self, user_id, experiment_id)
        digest = canonical_result(result)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            source = db.get(NiftyResearchExperiment, (user_id, experiment_id))
            if source is None or source.sha256 != result["definition_sha256"]:
                raise StateConflict("Experiment identity changed")
            existing = db.get(NiftyResearchResult, (user_id, experiment_id))
            if existing is None:
                db.add(
                    NiftyResearchResult(
                        user_id=user_id,
                        experiment_id=experiment_id,
                        payload=result,
                        sha256=digest,
                        created_at=now,
                    )
                )
            elif existing.sha256 != digest or canonical_result(existing.payload) != digest:
                raise StateConflict("Immutable research result differs; create a new experiment")
        return {"result": result, "sha256": digest}

    def research_inspection(self, user_id, experiment_id):
        from database.nifty_algo_db import NiftyResearchResult
        from services.nifty_algo.replay_lab import canonical_result

        with self.sessions() as db:
            row = db.get(NiftyResearchResult, (user_id, experiment_id))
            if row is None:
                return None
            if canonical_result(row.payload) != row.sha256:
                raise ValueError("Research result integrity failed")
            from copy import deepcopy

            return {"result": deepcopy(row.payload), "sha256": row.sha256}

    def trade_detail(self, user_id, trade_id):
        from database.nifty_algo_db import (
            NiftyEvent,
            NiftyExitStudy,
            NiftyOrder,
            NiftyTrade,
            _instant,
        )

        with self.sessions() as db:
            row = db.get(NiftyTrade, trade_id)
            if row is None or row.user_id != user_id:
                return None
            entry = db.get(NiftyOrder, (user_id, row.entry_order_id))
            exit_order = db.get(NiftyOrder, (user_id, row.exit_order_id))
            _, detail = fill_facts(row, entry, exit_order)
            protection = exit_order.payload.get("protection") or {}
            excursion = {}
            for name in (
                "highest_bid",
                "lowest_bid",
                "observation_count",
                "first_observed_at",
                "last_source_time",
                "max_observation_gap_seconds",
            ):
                excursion[name] = protection.get(name)
            high, low = protection.get("highest_bid"), protection.get("lowest_bid")
            detail["exit_effectiveness"] = {
                "basis": "SAMPLED_EXECUTABLE_BID_NOT_CONTINUOUS_MARKET_EXTREMA",
                "mfe_gross": str(max(Decimal(0), (Decimal(high) - row.entry_price) * row.quantity))
                if high
                else None,
                "mae_gross": str(max(Decimal(0), (row.entry_price - Decimal(low)) * row.quantity))
                if low
                else None,
                "gross_profit_capture": str(
                    row.gross / ((Decimal(high) - row.entry_price) * row.quantity)
                )
                if high and Decimal(high) > row.entry_price
                else None,
                "coverage": excursion,
            }
            detail["mode"] = "PAPER"
            detail["signal"] = entry.payload.get("signal_context")
            detail["configuration"] = entry.payload.get("configuration")
            detail["selection"] = entry.payload.get("sizing_plan")
            detail["entry_observation"] = entry.payload.get("fill_observation")
            detail["exit_observation"] = exit_order.payload.get("fill_observation")
            from services.nifty_algo.execution_quality import fill_quality

            detail["execution_quality"] = {
                "entry": fill_quality(entry),
                "exit": fill_quality(exit_order),
            }
            detail["protection"] = protection
            events = db.scalars(
                select(NiftyEvent)
                .where(
                    NiftyEvent.user_id == user_id,
                    NiftyEvent.created_at >= row.opened_at,
                    NiftyEvent.created_at <= row.closed_at,
                    NiftyEvent.kind.in_(
                        (
                            "PROFIT_LOCK_ACTIVATED",
                            "PROFIT_FLOOR_UNREPRESENTABLE",
                            "safety_incident",
                            "safety_acknowledged",
                            "safety_resolved",
                        )
                    ),
                )
                .order_by(NiftyEvent.id)
                .limit(100)
            ).all()
            detail["timeline"] = [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "at": _instant(e.created_at),
                    "code": e.payload.get("code"),
                    "incident_id": e.payload.get("id"),
                }
                for e in events
            ]
            study = db.get(NiftyExitStudy, (user_id, row.id))
            detail["post_exit"] = (
                study.payload
                if study
                else {"status": "UNAVAILABLE", "reason": "NO_VALIDATED_POST_EXIT_OBSERVATIONS"}
            )
            detail["limitations"] = [
                "Sampled observations can miss price extremes.",
                "Later favorable movement does not prove an earlier exit was wrong.",
                "Timeline links incidents by time window, not proven causality.",
            ]
            return detail

    def exit_study_targets(self, user_id, start, end):
        from database.nifty_algo_db import NiftyOrder, NiftyTrade, _instant

        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyTrade)
                .where(
                    NiftyTrade.user_id == user_id,
                    NiftyTrade.closed_at >= start,
                    NiftyTrade.closed_at < end,
                )
                .order_by(NiftyTrade.id)
                .limit(10)
            ).all()
            return [
                {
                    "id": r.id,
                    "closed_at": _instant(r.closed_at),
                    "exit_price": str(r.exit_price),
                    "instrument": db.get(NiftyOrder, (user_id, r.entry_order_id)).payload[
                        "instrument"
                    ],
                }
                for r in rows
            ]

    def observe_exit_study(self, user_id, trade_id, quote, now, close, calendar_id):
        from database.nifty_algo_db import NiftyExitStudy, NiftyOrder, NiftyTrade, _instant

        if not isinstance(quote, Quote) or now.tzinfo is None or close.tzinfo is None:
            raise ValueError("Validated dated observations and effective close required")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            trade = db.get(NiftyTrade, trade_id)
            if trade is None or trade.user_id != user_id:
                raise LookupError("Trade not found")
            instrument = Instrument.model_validate(
                db.get(NiftyOrder, (user_id, trade.entry_order_id)).payload["instrument"]
            )
            closed = datetime.fromisoformat(_instant(trade.closed_at))
            if (
                quote.token != instrument.token
                or quote.bid is None
                or quote.bid_size <= 0
                or not closed < quote.source_time <= quote.received_time <= now <= close
                or not 0 <= (now - quote.source_time).total_seconds() <= 2
            ):
                return False
            row = db.get(NiftyExitStudy, (user_id, trade_id))
            payload = (
                dict(row.payload)
                if row
                else {
                    "status": "SAMPLING",
                    "basis": "VALIDATED_BID_SAMPLES_ONLY",
                    "samples": 0,
                    "session_close": close.astimezone(UTC).isoformat(),
                    "calendar_id": calendar_id,
                    "max_gap_seconds": 0,
                    "last_source_time": closed.isoformat(),
                    "checkpoints": {},
                    "lowest_bid": str(quote.bid),
                    "highest_bid": str(quote.bid),
                }
            )
            if (
                payload["session_close"] != close.astimezone(UTC).isoformat()
                or payload["calendar_id"] != calendar_id
            ):
                return False  # A changed calendar must be reviewed, never silently restated.
            previous = datetime.fromisoformat(payload["last_source_time"])
            if quote.source_time <= previous:
                return False
            payload["samples"] += 1
            payload["max_gap_seconds"] = max(
                payload["max_gap_seconds"], (quote.source_time - previous).total_seconds()
            )
            payload["lowest_bid"] = str(min(Decimal(payload["lowest_bid"]), quote.bid))
            payload["highest_bid"] = str(max(Decimal(payload["highest_bid"]), quote.bid))
            payload["last_source_time"] = quote.source_time.isoformat()
            elapsed = (quote.source_time - closed).total_seconds()
            for seconds in (300, 900, 1800):
                if seconds <= elapsed <= seconds + 2 and str(seconds) not in payload["checkpoints"]:
                    payload["checkpoints"][str(seconds)] = {
                        "bid": str(quote.bid),
                        "source_time": quote.source_time.isoformat(),
                    }
            if row is None:
                row = NiftyExitStudy(user_id=user_id, trade_id=trade_id)
                db.add(row)
            row.payload = payload
            return True
