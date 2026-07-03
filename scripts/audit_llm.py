#!/usr/bin/env python3
"""Join the LLM cross-check labels back onto their source text for auditing.

The LLM pass (``data/labeled_llm/<run>.jsonl``) stores only judgments keyed by
record id -- it carries no text, so a reader cannot see *why* a record was
labeled without re-joining the normalized snapshot (which is gitignored because
it is bulky and re-derivable). This script produces a single committed artifact,
``data/labeled_llm/<run>.audit.jsonl``, that places each LLM judgment next to the
verbatim text and permalink it was made from, so every label is auditable from a
fresh clone with no network access.

Deterministic: records are emitted sorted by id, so re-running yields a clean
diff. Standard library only.

Usage:
    python scripts/audit_llm.py [<run_id>]

With no argument the latest run under data/labeled_llm/ is used.
"""
from __future__ import annotations

import glob
import json
import os
import sys

LABELED_DIR = "data/labeled_llm"
NORMALIZED_DIR = "data/normalized"

# Fields copied from the LLM label; everything else in the audit row is context.
_LABEL_FIELDS = ("doc_relevant", "aspects", "feelings", "expectation", "polarity")
# Context fields lifted verbatim from the normalized record.
_CONTEXT_FIELDS = ("source", "url", "created_utc", "title", "text")


def _latest_run() -> str:
    files = [
        f
        for f in glob.glob(os.path.join(LABELED_DIR, "*.jsonl"))
        if not f.endswith(".audit.jsonl")
    ]
    if not files:
        raise SystemExit(f"no LLM label files in {LABELED_DIR}/")
    # run ids are UTC timestamps, so lexical sort == chronological
    return os.path.splitext(os.path.basename(sorted(files)[-1]))[0]


def _load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str]) -> int:
    run = argv[1] if len(argv) > 1 else _latest_run()

    labels_path = os.path.join(LABELED_DIR, f"{run}.jsonl")
    normalized_path = os.path.join(NORMALIZED_DIR, f"{run}.jsonl")
    if not os.path.exists(labels_path):
        raise SystemExit(f"missing LLM labels: {labels_path}")
    if not os.path.exists(normalized_path):
        raise SystemExit(
            f"missing normalized snapshot: {normalized_path}\n"
            "The normalized data is gitignored; re-run `collect` for this run id "
            "to regenerate it before building the audit trail."
        )

    by_id = {r["id"]: r for r in _load_jsonl(normalized_path)}
    labels = _load_jsonl(labels_path)

    rows: list[dict] = []
    missing: list[str] = []
    for lab in labels:
        rec = by_id.get(lab["id"])
        if rec is None:
            missing.append(lab["id"])
            continue
        row = {"id": lab["id"]}
        row.update({k: rec.get(k) for k in _CONTEXT_FIELDS})
        row["llm"] = {k: lab.get(k) for k in _LABEL_FIELDS}
        rows.append(row)

    rows.sort(key=lambda r: r["id"])

    out_path = os.path.join(LABELED_DIR, f"{run}.audit.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"run {run}: wrote {len(rows)} audit rows -> {out_path}")
    if missing:
        print(f"WARNING: {len(missing)} labeled ids not found in normalized snapshot")
        for mid in missing[:10]:
            print(f"  missing: {mid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
