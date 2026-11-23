import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from pydantic import ValidationError

from src.errors import BatchPersistenceError, PersistenceError
from src.schemas import ArbitrationResult, CriticType


class ArbitrationStore:
    """SQLite audit store. Each operation uses its own short-lived connection."""

    def __init__(self, database_path: str) -> None:
        self._is_memory = database_path == ":memory:"
        self.database_path = f"file:arbitration-{uuid4()}?mode=memory&cache=shared" if self._is_memory else database_path
        self._anchor = sqlite3.connect(self.database_path, uri=True) if self._is_memory else None
        if not self._is_memory:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, uri=self._is_memory)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS arbitrations (
                    arbitration_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    overall_score INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_arbitrations_created ON arbitrations(created_at DESC)")
        except sqlite3.Error as exc:
            raise PersistenceError("Could not initialize SQLite audit storage.") from exc

    def save(self, result: ArbitrationResult) -> None:
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO arbitrations VALUES (?, ?, ?, ?, ?)",
                    (result.arbitration_id, result.created_at, result.final_verdict.verdict.value,
                     result.final_verdict.overall_score, result.model_dump_json()),
                )
        except sqlite3.Error as exc:
            raise PersistenceError("Could not save arbitration record.") from exc

    def save_many(self, results: list[ArbitrationResult]) -> None:
        """Persist a batch atomically; any failed insert rolls back the batch."""
        if not results:
            return
        try:
            with self._connection() as connection:
                connection.executemany(
                    "INSERT INTO arbitrations VALUES (?, ?, ?, ?, ?)",
                    [
                        (result.arbitration_id, result.created_at, result.final_verdict.verdict.value,
                         result.final_verdict.overall_score, result.model_dump_json())
                        for result in results
                    ],
                )
        except sqlite3.Error as exc:
            raise BatchPersistenceError("Could not save arbitration batch; no batch records were committed.") from exc

    def get(self, arbitration_id: str) -> ArbitrationResult | None:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT payload_json FROM arbitrations WHERE arbitration_id = ?", (arbitration_id,)).fetchone()
            return ArbitrationResult.model_validate_json(row["payload_json"]) if row else None
        except (sqlite3.Error, ValueError, ValidationError) as exc:
            raise PersistenceError("Could not read arbitration record.") from exc

    def list(self, limit: int = 100, offset: int = 0) -> list[ArbitrationResult]:
        try:
            with self._connection() as connection:
                rows = connection.execute("SELECT payload_json FROM arbitrations ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [ArbitrationResult.model_validate_json(row["payload_json"]) for row in rows]
        except (sqlite3.Error, ValueError, ValidationError) as exc:
            raise PersistenceError("Could not list arbitration records.") from exc

    def analytics(self) -> dict:
        records: list[ArbitrationResult] = []
        offset = 0
        while True:
            page = self.list(limit=1000, offset=offset)
            records.extend(page)
            if len(page) < 1000:
                break
            offset += len(page)
        total = len(records)
        critic_counts: dict[str, int] = {}
        issue_counts: dict[str, int] = {}
        failures_by_type: dict[str, int] = {}
        failures_by_critic: dict[str, int] = {}
        overrides: dict[str, int] = {}
        final_score_counts: dict[str, int] = {}
        latencies: list[float] = []
        critic_latencies: dict[str, list[float]] = {}
        comparable_pairs = 0
        disagreeing_pairs = 0
        for record in records:
            latencies.append(record.timings_ms.get("total", 0.0))
            score_key = str(record.final_verdict.overall_score)
            final_score_counts[score_key] = final_score_counts.get(score_key, 0) + 1
            for critic_type in CriticType:
                name = critic_type.value
                value = record.timings_ms.get(f"{name}_ms")
                if value is not None:
                    critic_latencies.setdefault(name, []).append(value)
            for report in record.critic_reports:
                critic_counts[report.critic_type.value] = critic_counts.get(report.critic_type.value, 0) + len(report.issues)
                for issue in report.issues:
                    issue_counts[issue.category] = issue_counts.get(issue.category, 0) + 1
            report_types = sorted({report.critic_type.value for report in record.critic_reports})
            possible_pairs = set(combinations(report_types, 2))
            observed_disagreements = {
                tuple(sorted((disagreement.critic_a.value, disagreement.critic_b.value)))
                for disagreement in record.disagreements
            }
            comparable_pairs += len(possible_pairs)
            disagreeing_pairs += len(possible_pairs & observed_disagreements)
            for error in record.errors:
                parts = error.split(": ", 2)
                critic_name = parts[0] if len(parts) > 1 else "unknown"
                failure_type = parts[1] if len(parts) > 1 else "UnknownError"
                failures_by_critic[critic_name] = failures_by_critic.get(critic_name, 0) + 1
                failures_by_type[failure_type] = failures_by_type.get(failure_type, 0) + 1
            if record.final_verdict.rationale and record.final_verdict.rationale.startswith("Fallback used:"):
                failures_by_type["adjudication_fallback"] = failures_by_type.get("adjudication_fallback", 0) + 1
            for flag in record.final_verdict.dismissed_flags:
                overrides[flag.critic_type.value] = overrides.get(flag.critic_type.value, 0) + 1
        agreement_rate = (comparable_pairs - disagreeing_pairs) / comparable_pairs if comparable_pairs else 0.0
        disagreement_rate = disagreeing_pairs / comparable_pairs if comparable_pairs else 0.0
        return {
            "total_arbitrations": total,
            "average_score": round(sum(r.final_verdict.overall_score for r in records) / total, 2) if total else 0,
            "agreement_rate": round(agreement_rate, 3),
            "disagreement_rate": round(disagreement_rate, 3),
            "comparable_critic_pairs": comparable_pairs,
            "disagreeing_critic_pairs": disagreeing_pairs,
            "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "average_critic_latency_ms": {name: round(sum(values) / len(values), 2) for name, values in critic_latencies.items()},
            "issues_by_critic": critic_counts,
            "issues_by_category": issue_counts,
            "overruled_flags_by_critic": overrides,
            "final_scores": dict(sorted(final_score_counts.items(), key=lambda item: int(item[0]))),
            "failures_by_type": failures_by_type,
            "failures_by_critic": failures_by_critic,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
