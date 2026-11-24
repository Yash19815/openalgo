"""Explicit separate research process. Never runs in a protection/request worker."""

from datetime import UTC, datetime

from utils.logging import get_logger

from .execution_replay import compare, identity, instant
from .research import recording_cursor
from .safe_logging import log_failure

logger = get_logger(__name__)


def run_experiment(store, user_id, experiment_id):
    definition = store.experiment(user_id, experiment_id)
    if definition is None:
        raise LookupError("Experiment not found")
    snapshot = definition["snapshot"]
    dataset = snapshot["dataset"]
    manifests = dataset.get("recordings", [dataset])
    events = []
    for manifest in manifests:
        cursor = recording_cursor(
            store,
            user_id,
            manifest["id"],
            expected_count=manifest["count"],
            expected_sha256=manifest["content_sha256"],
        )
        if cursor.manifest != manifest:
            raise ValueError("Pinned recording changed")
        while True:
            page = cursor.advance(instant(manifest["sealed_at"]))
            if not page["items"]:
                break
            events.extend({**row, "recording_id": manifest["id"]} for row in page["items"])
    events.sort(
        key=lambda row: (instant(row["available_at"]), row["recording_id"], row["sequence"])
    )
    baseline = manifests[0]["configuration"]
    if any(m["configuration"] != baseline for m in manifests):
        raise ValueError("Comparison requires one pinned baseline configuration")
    result = compare(events, baseline, snapshot["configuration"], snapshot["splits"])
    return {
        **result,
        "definition_sha256": definition["sha256"],
        "experiment_id": experiment_id,
        "source_sha256": identity(manifests),
        "provenance": "RECORDED_EVIDENCE_NOT_PROVIDER_CERTIFICATION",
    }


class ReplayWorker:
    def __init__(self, store, user_id, clock=None):
        self.store, self.user_id = store, user_id
        self.clock = clock or (lambda: datetime.now(UTC))

    def tick(self):
        claim = self.store.claim_execution_research(self.user_id, self.clock())
        if claim is None:
            return {"status": "IDLE"}
        try:
            result = run_experiment(self.store, self.user_id, claim["experiment_id"])
        except (ValueError, LookupError, OSError) as error:
            result = {
                "mode": "RESEARCH",
                "status": "REFUSED_EVIDENCE_INTEGRITY",
                "performance": None,
                "missing": [
                    "FRAME_CONFIGURATION_ID_MISMATCH"
                    if str(error) == "FRAME_CONFIGURATION_ID_MISMATCH"
                    else "PINNED_SOURCE_INTEGRITY_OR_REQUIRED_TYPED_EVIDENCE"
                ],
                "active_settings_changed": False,
            }
        self.store.finish_execution_research(self.user_id, claim, result, self.clock())
        return {"status": "COMPLETE"}


def main():
    import argparse
    import os
    import signal
    import time

    from dotenv import load_dotenv

    from database.engine_factory import create_db_engine
    from database.nifty_algo_db import NiftyStore

    parser = argparse.ArgumentParser(description="Isolated NIFTY research worker; no orders")
    parser.add_argument("--user", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    engine = create_db_engine(os.environ["DATABASE_URL"])
    store = NiftyStore(engine)
    store.initialize()
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        worker = ReplayWorker(store, args.user)
        while not stopping:
            try:
                worker.tick()
            except Exception as error:
                log_failure(logger, "NIFTY research cycle; durable claim retained", error)
            if args.once:
                break
            time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
