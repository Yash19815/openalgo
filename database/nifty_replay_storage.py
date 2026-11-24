"""Owned research jobs and explicit verified archival. No trading-ledger writes."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, or_, select


class ArchivePages:
    def __init__(self, bundle):
        self.bundle = bundle

    def recording_page(self, user_id, recording_id, *, after=0, limit=100, **kwargs):
        rows = self.bundle["items"][after : after + limit]
        return {
            "manifest": deepcopy(self.bundle["manifest"]),
            "items": deepcopy(rows),
            "next_after": rows[-1]["sequence"] if rows else after,
        }


class ReplayStorage:
    def archived_recordings(self, user_id):
        from database.nifty_algo_db import NiftyResearchCapture, NiftyResearchRecording

        with self.sessions() as db:
            rows = db.execute(
                select(NiftyResearchRecording, NiftyResearchCapture)
                .outerjoin(
                    NiftyResearchCapture,
                    (NiftyResearchCapture.user_id == NiftyResearchRecording.user_id)
                    & (NiftyResearchCapture.recording_id == NiftyResearchRecording.id),
                )
                .where(
                    NiftyResearchRecording.user_id == user_id,
                    NiftyResearchRecording.status == "ARCHIVED",
                )
                .order_by(NiftyResearchRecording.starts_at.desc())
                .limit(50)
            ).all()
            return [self._recording_dict(row, capture) for row, capture in rows]

    def create_execution_comparison(
        self, user_id, sources, configuration, train_end, validation_end, now
    ):
        from database.nifty_algo_db import NiftyResearchExperiment
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.execution_replay import (
            ENGINE,
            identity,
            instant,
            research_configuration,
        )

        if (
            not isinstance(sources, list)
            or not 1 <= len(sources) <= 20
            or any(not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in sources)
            or len({s["id"] for s in sources}) != len(sources)
        ):
            raise ValueError("One to twenty distinct owned recordings required")
        manifests = []
        for source in sources:
            if set(source) != {"id", "count", "content_sha256"}:
                raise ValueError("Pinned recording identities required")
            # Definition creation pins bounded metadata only. The isolated worker
            # verifies the entire digest chain before calculating any result.
            page = self.recording_page(user_id, source["id"], limit=1)
            manifest = page["manifest"]
            if (
                manifest["status"] != "SEALED"
                or type(source["count"]) is not int
                or manifest["count"] != source["count"]
                or manifest["content_sha256"] != source["content_sha256"]
            ):
                raise ValueError("Sealed pinned recording identity changed")
            manifests.append(manifest)
        manifests.sort(key=lambda m: (m["starts_at"], m["id"]))
        if any(m["configuration_id"] != manifests[0]["configuration_id"] for m in manifests):
            raise ValueError("One baseline configuration required")
        start = min(instant(m["starts_at"]) for m in manifests)
        end = max(min(instant(m["ends_at"]), instant(m["sealed_at"])) for m in manifests)
        train_end, validation_end = instant(train_end), instant(validation_end)
        if not start < train_end < validation_end < end or any(
            instant(m["sealed_at"]) > now for m in manifests
        ):
            raise ValueError("Ordered splits within sealed evidence required")
        config = StrategyConfig.model_validate(configuration)
        research_configuration(manifests[0]["configuration"], config)
        boundaries = (start, train_end, validation_end, end)
        snapshot = {
            "schema_version": 2,
            "engine_version": ENGINE,
            "dataset": {"recordings": manifests, "content_sha256": identity(manifests)},
            "configuration": config.model_dump(mode="json"),
            "configuration_id": config.version_id,
            "splits": [
                {"kind": kind, "start": a.isoformat(), "end": b.isoformat()}
                for kind, a, b in zip(
                    ("TRAIN", "VALIDATION", "TEST"), boundaries, boundaries[1:], strict=False
                )
            ],
            "interval": "[start,end)",
        }
        if len(dumps(snapshot).encode()) > 1048576:
            raise ValueError("Comparison definition exceeds bounds")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            count = db.scalar(
                select(func.count())
                .select_from(NiftyResearchExperiment)
                .where(NiftyResearchExperiment.user_id == user_id)
            )
            if count >= 50:
                raise ValueError("Experiment quota reached")
            row = NiftyResearchExperiment(
                user_id=user_id,
                id=uuid4().hex,
                created_at=now,
                snapshot=snapshot,
                sha256=identity(snapshot),
            )
            db.add(row)
            return self._experiment_dict(row)

    def queue_execution_research(self, user_id, experiment_id, now):
        from database.nifty_algo_db import NiftyExecutionResearch, NiftyResearchExperiment

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            if db.get(NiftyResearchExperiment, (user_id, experiment_id)) is None:
                raise LookupError("Experiment not found")
            row = db.get(NiftyExecutionResearch, (user_id, experiment_id))
            if row is None:
                db.add(
                    NiftyExecutionResearch(
                        user_id=user_id,
                        experiment_id=experiment_id,
                        status="PENDING",
                        updated_at=now,
                    )
                )
        return self.execution_research(user_id, experiment_id)

    def execution_research(self, user_id, experiment_id):
        from database.nifty_algo_db import NiftyExecutionResearch
        from services.nifty_algo.replay_lab import canonical_result

        with self.sessions() as db:
            row = db.get(NiftyExecutionResearch, (user_id, experiment_id))
            if row is None:
                return None
            if row.payload is not None and canonical_result(row.payload) != row.sha256:
                raise ValueError("Execution research integrity failed")
            return {
                "status": row.status,
                "result": deepcopy(row.payload),
                "sha256": row.sha256,
                "worker": "SEPARATE_RESEARCH_PROCESS",
                "active_settings_changed": False,
            }

    def claim_execution_research(self, user_id, now):
        from database.nifty_algo_db import NiftyExecutionResearch

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftyExecutionResearch)
                .where(
                    NiftyExecutionResearch.user_id == user_id,
                    or_(
                        NiftyExecutionResearch.status == "PENDING",
                        (NiftyExecutionResearch.status == "RUNNING")
                        & (NiftyExecutionResearch.claimed_until <= now),
                    ),
                )
                .order_by(NiftyExecutionResearch.updated_at)
                .limit(1)
            )
            if row is None:
                return None
            row.status, row.claim_token = "RUNNING", uuid4().hex
            row.claimed_until, row.updated_at = now + timedelta(minutes=15), now
            return {"experiment_id": row.experiment_id, "claim_token": row.claim_token}

    def finish_execution_research(self, user_id, claim, result, now):
        from database.nifty_algo_db import NiftyExecutionResearch, StateConflict, _instant
        from services.nifty_algo.replay_lab import canonical_result

        digest = canonical_result(result)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyExecutionResearch, (user_id, claim["experiment_id"]))
            if (
                row is None
                or row.status != "RUNNING"
                or row.claim_token != claim["claim_token"]
                or datetime.fromisoformat(_instant(row.claimed_until)) <= now
            ):
                raise StateConflict("Research claim changed")
            row.payload, row.sha256, row.status, row.updated_at = result, digest, "COMPLETE", now

    def _archive_path(self, user_id, recording_id):
        from re import fullmatch

        if fullmatch(r"[a-f0-9]{32}", recording_id) is None:
            raise ValueError("Invalid archive identity")
        root = Path(self.report_dir).resolve() / "research-archives"
        path = root / sha256(user_id.encode()).hexdigest() / (recording_id + ".json")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Archive escaped root")
        return path

    def load_archived_recording(self, user_id, recording_id):
        from database.nifty_algo_db import NiftyRecordingArchive, NiftyResearchRecording

        with self.sessions() as db:
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            archive = db.get(NiftyRecordingArchive, (user_id, recording_id))
            if row is None or row.status != "ARCHIVED":
                return None
            if archive is None:
                raise ValueError("Archive metadata missing")
            expected = archive.sha256
        path = self._archive_path(user_id, recording_id)
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Archive exceeds bounds")
        with path.open("rb") as stream:
            data = stream.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024 or sha256(data).hexdigest() != expected:
            raise ValueError("Archive integrity failed")
        bundle = loads(data)
        if (
            set(bundle) != {"schema_version", "manifest", "items", "samples"}
            or bundle["schema_version"] != 1
            or bundle["manifest"]["id"] != recording_id
        ):
            raise ValueError("Archive identity failed")
        return bundle

    def archive_recording(self, user_id, recording_id, now):
        from database.nifty_algo_db import (
            NiftyRecordingArchive,
            NiftyResearchObservation,
            NiftyResearchRecording,
            NiftyResearchSample,
            StateConflict,
        )
        from services.nifty_algo.reports import write_atomic
        from services.nifty_algo.research import recording_cursor

        existing = self.load_archived_recording(user_id, recording_id)
        if existing is not None:
            return {"status": "ARCHIVED", "content_sha256": existing["manifest"]["content_sha256"]}
        page = self.recording_page(user_id, recording_id)
        if page is None:
            raise LookupError("Recording not found")
        manifest = page["manifest"]
        cursor = recording_cursor(
            self,
            user_id,
            recording_id,
            expected_count=manifest["count"],
            expected_sha256=manifest["content_sha256"],
        )
        items = []
        while True:
            rows = cursor.advance(datetime.fromisoformat(manifest["sealed_at"]))["items"]
            if not rows:
                break
            items.extend(rows)
        with self.sessions() as db:
            samples = list(
                db.scalars(
                    select(NiftyResearchSample.sha256).where(
                        NiftyResearchSample.user_id == user_id,
                        NiftyResearchSample.recording_id == recording_id,
                    )
                ).all()
            )
        bundle = {
            "schema_version": 1,
            "manifest": manifest,
            "items": items,
            "samples": sorted(samples),
        }
        data = dumps(bundle, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Archive exceeds bounds")
        path = self._archive_path(user_id, recording_id)
        write_atomic(path, data)
        # The file is durable and verified before any database evidence is retired.
        if path.read_bytes() != data:
            raise ValueError("Archive write failed verification")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            if (
                row is None
                or row.status != "SEALED"
                or row.content_sha256 != manifest["content_sha256"]
            ):
                raise StateConflict("Recording changed during archival")
            archive = db.get(NiftyRecordingArchive, (user_id, recording_id))
            if archive is None:
                archive = NiftyRecordingArchive(
                    user_id=user_id,
                    recording_id=recording_id,
                    sha256=sha256(data).hexdigest(),
                    path=path.name,
                    created_at=now,
                )
                db.add(archive)
            else:
                archive.sha256 = sha256(data).hexdigest()
            db.execute(
                delete(NiftyResearchObservation).where(
                    NiftyResearchObservation.user_id == user_id,
                    NiftyResearchObservation.recording_id == recording_id,
                )
            )
            db.execute(
                delete(NiftyResearchSample).where(
                    NiftyResearchSample.user_id == user_id,
                    NiftyResearchSample.recording_id == recording_id,
                )
            )
            row.status = "ARCHIVED"
        return {
            "status": "ARCHIVED",
            "content_sha256": manifest["content_sha256"],
            "archive_sha256": sha256(data).hexdigest(),
        }

    def restore_recording(self, user_id, recording_id, now):
        from database.nifty_algo_db import (
            NiftyResearchObservation,
            NiftyResearchRecording,
            NiftyResearchSample,
            StateConflict,
        )
        from services.nifty_algo.research import recording_cursor

        bundle = self.load_archived_recording(user_id, recording_id)
        if bundle is None:
            raise ValueError("Archived recording not found")
        manifest = bundle["manifest"]
        recording_cursor(
            ArchivePages(bundle),
            user_id,
            recording_id,
            expected_count=manifest["count"],
            expected_sha256=manifest["content_sha256"],
        )
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            count = db.scalar(
                select(func.count())
                .select_from(NiftyResearchRecording)
                .where(
                    NiftyResearchRecording.user_id == user_id,
                    NiftyResearchRecording.status != "ARCHIVED",
                )
            )
            if row is None or row.status != "ARCHIVED" or count >= 20:
                raise StateConflict("Restore state changed or active recording quota reached")
            for item in bundle["items"]:
                db.add(
                    NiftyResearchObservation(
                        user_id=user_id,
                        recording_id=recording_id,
                        sequence=item["sequence"],
                        sha256=item["sha256"],
                        available_at=datetime.fromisoformat(item["available_at"]),
                        payload={k: v for k, v in item.items() if k != "sequence"},
                    )
                )
            for digest in bundle["samples"]:
                db.add(
                    NiftyResearchSample(user_id=user_id, recording_id=recording_id, sha256=digest)
                )
            row.status = "SEALED"
        return {"status": "SEALED", "content_sha256": manifest["content_sha256"]}
