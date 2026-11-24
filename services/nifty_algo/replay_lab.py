"""Causal evidence inspection over sealed experiments. Never claims invented fills."""

from datetime import datetime
from hashlib import sha256
from json import dumps

from .research import recording_cursor

ENGINE = "quote-evidence-inspection-v1"
MISSING = (
    "FUTURES_CANDLES",
    "HISTORICAL_PCR",
    "POINT_IN_TIME_SIGNAL_INPUTS",
    "CONTINUOUS_PROTECTION_PRICE_COVERAGE",
)


def experiment_cursor(store, user_id, experiment_id):
    definition = store.experiment(user_id, experiment_id)
    if definition is None:
        raise LookupError("Experiment not found")
    dataset = definition["snapshot"]["dataset"]
    if "recordings" in dataset:
        raise ValueError("Multi-session bundles use the isolated execution comparison worker")
    cursor = recording_cursor(
        store,
        user_id,
        dataset["id"],
        expected_count=dataset["count"],
        expected_sha256=dataset["content_sha256"],
    )
    if cursor.manifest != dataset:
        raise ValueError("Experiment dataset identity changed")
    return definition, cursor


def inspect_experiment(store, user_id, experiment_id):
    definition, cursor = experiment_cursor(store, user_id, experiment_id)
    snapshot = definition["snapshot"]
    dataset = snapshot["dataset"]
    clock = datetime.fromisoformat(dataset["sealed_at"])
    instruments, samples, split_counts = {}, 0, {s["kind"]: 0 for s in snapshot["splits"]}
    while True:
        page = cursor.advance(clock)
        if not page["items"]:
            break
        for item in page["items"]:
            if item["kind"] != "QUOTE":
                continue  # Financial replay consumes frames through its separate evidence gate.
            samples += 1
            quote = item["payload"]
            token = quote["token"]
            available = datetime.fromisoformat(item["available_at"])
            for split in snapshot["splits"]:
                if (
                    datetime.fromisoformat(split["start"])
                    <= available
                    < datetime.fromisoformat(split["end"])
                ):
                    split_counts[split["kind"]] += 1
            row = instruments.setdefault(
                token,
                {
                    "samples": 0,
                    "first_available_at": item["available_at"],
                    "last_available_at": item["available_at"],
                    "max_gap_seconds": 0,
                    "executable_bid_ask_samples": 0,
                },
            )
            row["max_gap_seconds"] = max(
                row["max_gap_seconds"],
                (available - datetime.fromisoformat(row["last_available_at"])).total_seconds(),
            )
            row["last_available_at"] = item["available_at"]
            row["samples"] += 1
            row["executable_bid_ask_samples"] += int(
                quote["bid"] is not None
                and quote["ask"] is not None
                and quote["bid_size"] > 0
                and quote["ask_size"] > 0
            )
    return {
        "engine_version": ENGINE,
        "mode": "RESEARCH",
        "fidelity": "QUOTE_EVIDENCE_ONLY",
        "experiment_id": experiment_id,
        "definition_sha256": definition["sha256"],
        "dataset_sha256": dataset["content_sha256"],
        "configuration_id": snapshot["configuration_id"],
        "samples": samples,
        "instruments": instruments,
        "split_counts": split_counts,
        "execution_eligible": False,
        "performance": None,
        "full_execution_refused": list(MISSING),
        "variants": [
            {
                "name": name,
                "trailing_distance_points": "1.5",
                "profit_lock": lock,
                "status": "REFUSED_MISSING_EVIDENCE",
                "performance": None,
            }
            for name, lock in (
                ("A_BASELINE", False),
                ("B_CURRENT", True),
                ("C_EXPERIMENTAL", "RESEARCH_SETTINGS_ONLY"),
            )
        ],
        "limitations": [
            "Hashes prove content identity, not provider authenticity.",
            "Observed quote samples do not establish continuous depth or achievable fills.",
            "No signal backtest or financial simulation is inferred from option quotes.",
            "Missing PCR prevents a complete five-indicator study.",
        ],
    }


def replay_page(store, user_id, experiment_id, *, as_of, after=0):
    definition, cursor = experiment_cursor(store, user_id, experiment_id)
    if type(after) is not int or not 0 <= after <= definition["snapshot"]["dataset"]["count"]:
        raise ValueError("Invalid replay position")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("Replay clock must include timezone")
    skipped = 0
    while skipped < after:
        page = cursor.advance(as_of, limit=min(100, after - skipped))
        if not page["items"]:
            raise ValueError("Replay position is ahead of available evidence")
        skipped += len(page["items"])
    page = cursor.advance(as_of)
    return {
        **page,
        "experiment_id": experiment_id,
        "definition_sha256": definition["sha256"],
        "performance": None,
    }


def canonical_result(result):
    encoded = dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 1048576:
        raise ValueError("Research result exceeds 1 MiB")
    return sha256(encoded).hexdigest()
