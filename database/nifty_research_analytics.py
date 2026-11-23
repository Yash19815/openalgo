"""Read existing fills and persist sampled exit research without a second ledger."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from services.nifty_algo.ledger_analytics import fill_facts
from services.nifty_algo.models import Instrument, Quote


class ResearchAnalyticsStore:
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
                "policy": "risk-approved-weighted-v1",
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
