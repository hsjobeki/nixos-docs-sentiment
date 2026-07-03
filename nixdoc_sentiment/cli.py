"""Command-line entrypoint.

Stages (each keyed by a run-id snapshot):
  collect   fetch sources    -> data/raw/<run>/, data/normalized/<run>.jsonl
  classify  label a snapshot -> data/labeled/<run>.jsonl
  aggregate summarize        -> data/metrics/<run>.json
  run       collect+classify+aggregate for one fresh snapshot
  report    print the trend across all data/metrics/*.json

`collect`/`run` mint a new run-id; `classify`/`aggregate` default to the latest
existing snapshot unless --run-id is given.
"""

from __future__ import annotations

import argparse
import sys

from nixdoc_sentiment import categories as C
from nixdoc_sentiment.aggregate import aggregate as aggregate_fn
from nixdoc_sentiment.classify import classify_record
from nixdoc_sentiment.collect import COLLECTORS
from nixdoc_sentiment.http import Http
from nixdoc_sentiment.report import format_report
from nixdoc_sentiment.schema import record_from_dict
from nixdoc_sentiment.sources import ALL_SOURCES, CollectConfig
from nixdoc_sentiment.store import (Layout, log, new_run_id, read_jsonl,
                                    write_json, write_jsonl)


def _config_from_args(args) -> CollectConfig:
    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    unknown = [s for s in sources if s not in ALL_SOURCES]
    if unknown:
        raise SystemExit(f"unknown source(s): {unknown}; valid: {list(ALL_SOURCES)}")
    cfg = CollectConfig(sources=sources, max_pages=args.max_pages,
                        max_topics=args.max_topics, request_delay=args.request_delay)
    if args.github_repos:
        cfg.github_repos = [r.strip() for r in args.github_repos.split(",") if r.strip()]
    if args.user_agent:
        cfg.user_agent = args.user_agent
    return cfg


def do_collect(layout: Layout, cfg: CollectConfig, run_id: str) -> int:
    http = Http(cfg.user_agent, delay=cfg.request_delay)
    all_records: dict[str, dict] = {}  # id -> record dict (dedup across sources)
    for source in cfg.sources:
        log(f"collecting {source} ...")
        raw, records = COLLECTORS[source](http, cfg)
        write_json(layout.raw_file(run_id, source), raw)
        for rec in records:
            all_records[rec.id] = rec.as_dict()
        log(f"  {source}: {len(records)} records")
    rows = [all_records[k] for k in sorted(all_records)]
    n = write_jsonl(layout.normalized(run_id), rows)
    log(f"snapshot {run_id}: {n} normalized records -> {layout.normalized(run_id)}")
    return n


def do_classify(layout: Layout, run_id: str) -> int:
    rows = read_jsonl(layout.normalized(run_id))
    labeled = [classify_record(record_from_dict(r)) for r in rows]
    n = write_jsonl(layout.labeled(run_id), labeled)
    relevant = sum(1 for r in labeled if r["doc_relevant"])
    log(f"classified {n} records ({relevant} doc-relevant) -> {layout.labeled(run_id)}")
    return n


def do_aggregate(layout: Layout, run_id: str) -> dict:
    labeled = read_jsonl(layout.labeled(run_id))
    metrics = aggregate_fn(labeled, run_id, C.SCHEME_VERSION)
    write_json(layout.metrics(run_id), metrics)
    log(f"metrics -> {layout.metrics(run_id)} "
        f"(relevant={metrics['total_relevant']}, "
        f"mean_polarity={metrics['mean_polarity']}, "
        f"not_met_rate={metrics['not_met_rate']})")
    return metrics


def _resolve_run(explicit: str | None, latest: str | None, stage: str) -> str:
    run = explicit or latest
    if not run:
        raise SystemExit(f"no snapshot for {stage}; run `collect` first "
                         "or pass --run-id")
    return run


def cmd_collect(args) -> int:
    layout = Layout(args.data_dir)
    cfg = _config_from_args(args)
    run_id = args.run_id or new_run_id()
    do_collect(layout, cfg, run_id)
    print(run_id)
    return 0


def cmd_classify(args) -> int:
    layout = Layout(args.data_dir)
    run = _resolve_run(args.run_id, layout.latest_normalized(), "classify")
    do_classify(layout, run)
    return 0


def cmd_aggregate(args) -> int:
    layout = Layout(args.data_dir)
    run = _resolve_run(args.run_id, layout.latest_labeled(), "aggregate")
    do_aggregate(layout, run)
    return 0


def cmd_run(args) -> int:
    layout = Layout(args.data_dir)
    cfg = _config_from_args(args)
    run_id = args.run_id or new_run_id()
    do_collect(layout, cfg, run_id)
    do_classify(layout, run_id)
    do_aggregate(layout, run_id)
    print(format_report(layout))
    return 0


def cmd_report(args) -> int:
    layout = Layout(args.data_dir)
    print(format_report(layout))
    return 0


def _add_collect_args(p) -> None:
    p.add_argument("--sources", default=",".join(ALL_SOURCES),
                   help="comma-separated: " + ",".join(ALL_SOURCES))
    p.add_argument("--max-pages", type=int, default=2,
                   help="pages per query (default 2)")
    p.add_argument("--max-topics", type=int, default=40,
                   help="Discourse full-topic fetches per run (default 40)")
    p.add_argument("--github-repos", default="",
                   help="override GitHub repos (comma-separated)")
    p.add_argument("--request-delay", type=float, default=1.0,
                   help="seconds between HTTP calls (default 1.0)")
    p.add_argument("--user-agent", default="",
                   help="override HTTP User-Agent")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nixdoc-sentiment",
        description="Reproducible sentiment analysis of NixOS documentation feedback")
    p.add_argument("--data-dir", default="data", help="data directory (default ./data)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("collect", help="fetch sources into a new snapshot")
    _add_collect_args(pc)
    pc.add_argument("--run-id", default=None)
    pc.set_defaults(func=cmd_collect)

    pcl = sub.add_parser("classify", help="label the latest (or --run-id) snapshot")
    pcl.add_argument("--run-id", default=None)
    pcl.set_defaults(func=cmd_classify)

    pa = sub.add_parser("aggregate", help="summarize the latest (or --run-id) snapshot")
    pa.add_argument("--run-id", default=None)
    pa.set_defaults(func=cmd_aggregate)

    pr = sub.add_parser("run", help="collect + classify + aggregate + report")
    _add_collect_args(pr)
    pr.add_argument("--run-id", default=None)
    pr.set_defaults(func=cmd_run)

    prep = sub.add_parser("report", help="print trend across all snapshots")
    prep.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
