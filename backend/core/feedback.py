"""Feedback loop — logs collaboration runs and scores for iterative improvement."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import structlog

from .config import settings

log = structlog.get_logger()


class FeedbackStore:
    def __init__(self, path: str = settings.feedback_db_path) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(
        self,
        task_id: str,
        domain: str,
        pipeline: list[str],
        messages: list[dict],
        scores: dict[str, float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": task_id,
            "domain": domain,
            "pipeline": pipeline,
            "messages": messages,
            "scores": scores,
            "metadata": metadata or {},
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
        log.info("feedback_logged", task_id=task_id, scores=scores)

    def load_all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def average_scores(self, domain: str | None = None) -> dict[str, float]:
        records = self.load_all()
        if domain:
            records = [r for r in records if r["domain"] == domain]
        if not records:
            return {}
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for r in records:
            for k, v in r["scores"].items():
                totals[k] = totals.get(k, 0.0) + v
                counts[k] = counts.get(k, 0) + 1
        return {k: totals[k] / counts[k] for k in totals}


feedback_store = FeedbackStore()
