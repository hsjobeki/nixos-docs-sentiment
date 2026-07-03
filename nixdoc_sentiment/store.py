"""On-disk layout, run identifiers, and JSON(L) IO.

Reproducibility model
---------------------
Each collection creates an immutable, UTC-stamped snapshot. Raw API responses
are written verbatim (audit trail); derived stages (normalized -> labeled ->
metrics) are pure functions of a snapshot. Re-running months later produces a
NEW snapshot; snapshots accumulate into a time series under ``data/metrics``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Sortable lexicographically == chronologically, so ``max()`` gives the latest.
_RUN_FMT = "%Y%m%dT%H%M%SZ"


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime(_RUN_FMT)


def log(msg: str) -> None:
    print(f"[nixdoc] {msg}", file=sys.stderr, flush=True)


class Layout:
    """Resolves paths under a data directory. No IO in the constructor."""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)

    def raw_dir(self, run: str) -> Path:
        return self.root / "raw" / run

    def raw_file(self, run: str, source: str) -> Path:
        return self.raw_dir(run) / f"{source}.json"

    def normalized(self, run: str) -> Path:
        return self.root / "normalized" / f"{run}.jsonl"

    def labeled(self, run: str) -> Path:
        return self.root / "labeled" / f"{run}.jsonl"

    def metrics(self, run: str) -> Path:
        return self.root / "metrics" / f"{run}.json"

    def metrics_dir(self) -> Path:
        return self.root / "metrics"

    def latest_normalized(self) -> str | None:
        return _latest_stem(self.root / "normalized", ".jsonl")

    def latest_labeled(self) -> str | None:
        return _latest_stem(self.root / "labeled", ".jsonl")


def _latest_stem(directory: Path, ext: str) -> str | None:
    if not directory.exists():
        return None
    stems = [p.name[: -len(ext)] for p in directory.iterdir()
             if p.is_file() and p.name.endswith(ext)]
    return max(stems) if stems else None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys => byte-stable output for identical inputs (diff-friendly).
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
