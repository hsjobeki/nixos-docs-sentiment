# nixdoc-sentiment

Reproducible sentiment analysis of what people feel and expect about the
**NixOS documentation**. Built to be re-run every few months so you can see how
sentiment changes over time.

## What it does

Collects public feedback from several sources, then codes each item on three
orthogonal axes plus a signed polarity score:

1. **Aspect** — which facet of the docs the feedback is about: `discoverability`,
   `completeness`, `accuracy`, `onboarding`, `explanation`, `examples`,
   `structure`, `search`, `unofficial_reliance`, `tooling`.
2. **Feeling** — emotional tone: `frustration`, `confusion`, `anxiety`,
   `resignation`, `relief`, `delight`, `gratitude`.
3. **Expectation** — whether the docs met the reader's expectation:
   `met` / `not_met` / `exceeded` / `no_baseline` / `unclear`.
4. **Polarity** — a signed score in `[-1, 1]`.

Per-aspect `mean_polarity` and `not_met_rate` are the headline "where are we
meeting vs not meeting expectations" indicators.

## Findings: keyword lexicon vs LLM (snapshot 2026-07-03)

The reproducible pipeline uses a fast, transparent **keyword lexicon**. As a
cross-check, the same 1177-record snapshot (`20260703T153834Z`, Hacker News +
NixOS Discourse) was independently re-classified by an **LLM** (20 parallel
sub-agents) that can weigh negation, sarcasm, and — critically — *sentiment
target* (praise of an alternative like the Arch wiki is not delight about the
NixOS docs). The charts below show each label's share of doc-relevant records.

| indicator | lexicon | LLM |
| --- | --- | --- |
| records judged doc-relevant | 1038 | **375** |
| mean polarity | **+0.16** | **−0.24** |
| not-met rate | 19% | **60%** |
| delight (share) | 12.8% | **2.4%** |
| frustration (share) | 12.3% | **41.3%** |
| polarity sign agreement (shared-relevant records) | — | **35%** |

![Emotional profile: lexicon vs LLM](docs/charts/radar_feelings.svg)

![Documentation-aspect profile: lexicon vs LLM](docs/charts/radar_aspects.svg)

![Expectation outcomes: lexicon vs LLM](docs/charts/bar_expectation.svg)

**Takeaways.** (1) The lexicon's relevance gate over-includes ~3× — any mention
of "docs/manual/learning" counts. (2) On genuine documentation feedback the
sentiment **flips from mildly positive to net negative**; the LLM reads far more
frustration and almost no delight, and attributes ~60% of feedback to *unmet*
expectations. (3) **Completeness** (missing/undocumented things) is the dominant
complaint the lexicon badly undercounts (7% → 48%).

**Caveats.** The LLM is a different instrument, not ground truth, and is
**non-deterministic** (re-running gives different numbers) — which is exactly why
it lives outside the reproducible pipeline (`data/labeled_llm/`), and why the
lexicon remains the instrument for *trend* tracking. Both methods share the same
complaint-skewed corpus (people post about docs when annoyed), so the
method-vs-method comparison is fair even if absolute negativity is inflated.
Charts are regenerated from `data/compare/<run>.json` via
`python scripts/make_charts.py` (standard library only).


## Sources

| Source | Auth | Notes |
| --- | --- | --- |
| Hacker News (Algolia) | none | Global, so queries are NixOS-scoped. |
| NixOS Discourse | none | `discourse.nixos.org` search + full topics. |
| GitHub issues (`NixOS/nix.dev`) | optional `GITHUB_TOKEN` | Unauthenticated works but is rate-limited; set a token for real runs. |
| Reddit (`r/NixOS`) | optional OAuth | Public JSON is blocked from datacenter IPs; set `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` to use OAuth. Degrades gracefully (skips) otherwise. |

Any source that fails (rate limit, block, outage) is logged and skipped; a run
always completes with whatever was collected.

## Reproducibility model

- **Environment** is pinned by `flake.lock` (Nix). The tool is **standard-library
  only** — nothing outside the pinned Python interpreter is pulled in.
- **Data**: each collection writes a UTC-stamped, immutable snapshot. Raw API
  responses are stored verbatim (`data/raw/<run>/`) as an audit trail. Every
  later stage is a pure function of a snapshot, so re-classifying yesterday's
  raw data gives byte-identical output.
- **Instrument**: classification is a **transparent, versioned lexicon**, not an
  LLM. An LLM drifts between runs (model updates, non-determinism), which would
  make trends meaningless; a lexicon does not. Every label records exactly which
  cue words fired (`cues` field). When you change the scheme, bump
  `SCHEME_VERSION` in `nixdoc_sentiment/categories.py`; it is stamped into every
  labeled row and metrics file so you can tell which runs are comparable.
- **Time series**: `data/metrics/<run>.json` files accumulate and are committed
  to git. `report` reads them all to show change across runs.

## Usage

With Nix (reproducible):

```sh
nix run . -- run                 # collect + classify + aggregate + report
nix run . -- report              # trend across all snapshots
nix build                        # build + run the test suite
```

With a devshell / plain Python (stdlib only, no install needed):

```sh
nix develop                      # or just use any Python >= 3.11
python -m nixdoc_sentiment run --help
python -m nixdoc_sentiment run --sources hackernews,discourse --max-pages 2
python -m nixdoc_sentiment report
```

### Stages

Each stage operates on a run-id snapshot. `collect`/`run` mint a new run-id;
`classify`/`aggregate` default to the latest snapshot.

```sh
python -m nixdoc_sentiment collect     # -> data/raw/<run>/, data/normalized/<run>.jsonl ; prints <run>
python -m nixdoc_sentiment classify    # -> data/labeled/<run>.jsonl
python -m nixdoc_sentiment aggregate   # -> data/metrics/<run>.json
python -m nixdoc_sentiment report      # trend + latest breakdown + delta vs previous
```

### Recommended periodic run

```sh
GITHUB_TOKEN=... python -m nixdoc_sentiment run --max-pages 3
git add data/metrics && git commit -m "sentiment snapshot $(date -u +%F)"
```

Committing `data/metrics/` builds the historical trend; the bulky
`data/raw|normalized|labeled` are gitignored (raw is re-derivable audit data you
can archive separately).

## Limitations (read before trusting numbers)

- The classifier is a **transparent baseline**, not a calibrated model. It favours
  *stability across runs* over absolute accuracy — the right tradeoff for trend
  detection, but individual labels can be wrong. The `cues` field lets you audit
  any label.
- Lexicons live in `nixdoc_sentiment/categories.py` and are meant to be tuned.
  Ambiguous short tokens (e.g. `manual`, `hard`) are matched whole-word to avoid
  false positives like `manually` / `hardware`; most tokens use prefix stemming.
- **Negation/conditional** is handled with a short preceding-window heuristic
  (`SUPPRESSORS`): `not helpful` / `would love` do not fire. It is a window,
  not a parser, so it misses cross-clause and comparative cases. In particular,
  praise of an *alternative* ("the Arch wiki is amazing") can still read as a
  positive feeling because the lexicon has no notion of *subject* — a small,
  known residual (see the `cues` + `polarity` fields to spot it).
- Sampling is query-driven (see `sources.py`), so it reflects what those queries
  surface, not a census. Keep the queries fixed between runs for comparable trends.
- To validate/calibrate against ground truth, cross-check against the annual
  [Nix Community Survey](https://github.com/GuillaumeDesforges/nix-survey) and the
  [nix.dev documentation survey](https://github.com/NixOS/nix.dev/blob/master/maintainers/documentation-survey.md).

## Layout

```
nixdoc_sentiment/
  schema.py       normalized Record contract
  http.py         stdlib HTTP with throttle + retry
  textutil.py     HTML/entity stripping
  sources.py      source + query config (what we sample)
  collect.py      per-source collectors
  categories.py   versioned scheme + lexicons  <-- tune here, bump SCHEME_VERSION
  classify.py     deterministic classifier
  aggregate.py    per-run metrics
  report.py       cross-run trend view
  cli.py          collect / classify / aggregate / run / report
tests/            offline classifier tests (run during `nix build`)
scripts/
  make_charts.py  render the comparison SVGs (stdlib only)
docs/charts/      committed SVG charts shown above
data/compare/     lexicon-vs-LLM aggregates (chart source)
data/labeled_llm/ per-record LLM labels (non-reproducible cross-check)
```
