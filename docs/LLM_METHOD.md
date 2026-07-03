# LLM cross-check: method and rubric

This document describes the **out-of-band LLM classification** used as a
cross-check against the deterministic lexicon. It is deliberately **not part of
the reproducible pipeline**: an LLM pass is non-deterministic, so re-running it
yields different numbers and it cannot be the instrument of record for trends.
The lexicon (`nixdoc_sentiment/categories.py`, versioned by `SCHEME_VERSION`)
remains the instrument for tracking change over time. The LLM read exists to
answer one question: *does a smarter reader, one that understands negation,
sarcasm, and sentiment target, see the same picture the keyword lexicon does?*

Treat every number produced by this method as **directional, not measurement.**

## What was run

- **Input.** The same immutable snapshot the lexicon scored: `20260703T153834Z`
  (1177 normalized records, Hacker News + NixOS Discourse). No re-collection —
  both instruments read byte-identical text, so the comparison is fair.
- **Process.** The 1177 records were split into batches of 60 and classified by
  20 parallel LLM sub-agents, each applying the rubric below. Output is one JSON
  object per record, written to `data/labeled_llm/<run>.jsonl`.
- **Coverage.** Every input record received exactly one label (100% coverage,
  0 schema-invalid rows).
- **Scheme tag.** Each row carries `"scheme_version": "llm-1"`. Only rows sharing
  a scheme tag are comparable; an LLM run and a lexicon run are **never** merged,
  only compared side by side (`data/compare/<run>.json`).

## Label space

Identical taxonomy to the lexicon, so the two instruments are directly
comparable. Per record:

- **`doc_relevant`** (bool) — is this feedback actually *about the NixOS
  documentation* (as opposed to Nix the language, packaging, or an unrelated HN
  tangent)? Records judged `false` are dropped before aggregation.
- **`aspects`** (0+ of): `discoverability`, `completeness`, `accuracy`,
  `onboarding`, `explanation`, `examples`, `structure`, `search`,
  `unofficial_reliance`, `tooling`. Which facet(s) of the docs the feedback is
  about. Multi-label.
- **`feelings`** (0+ of): `frustration`, `confusion`, `anxiety`, `resignation`,
  `relief`, `delight`, `gratitude`.
- **`expectation`** (exactly one of): `met`, `not_met`, `exceeded`,
  `no_baseline`, `unclear` — did the docs meet the reader's expectation?
- **`polarity`** (float in `[-1, 1]`) — signed sentiment **toward the NixOS
  docs specifically**.

## Rubric / decision rules

These are the judgment rules the sub-agents applied. They encode the things a
keyword lexicon structurally cannot do:

1. **Score the subject, not the sentence.** Polarity and feelings must attribute
   to *the official NixOS docs*. Praise of an *alternative* to them ("the NixOS
   Wiki saved me, the manual didn't" or "just read someone's blog post instead")
   is **negative** toward the official docs, not delight, and is a strong
   `unofficial_reliance` signal — this is the single largest correction over the
   lexicon, which has no notion of subject.
2. **Honor negation and conditionals across the clause.** "not helpful",
   "wish the docs explained", "would love a guide" express a *gap*, not
   satisfaction. Score them as the unmet wish they are.
3. **Read sarcasm and understatement** by intent, not surface tokens
   ("great, another undocumented flag" is frustration, not delight).
4. **`expectation` requires a baseline.** Use `not_met` only when the reader
   expected something the docs failed to provide; `no_baseline` when they had no
   prior expectation; `unclear` when the text does not reveal one. Do not infer
   `not_met` from generic negativity.
5. **Relevance is strict.** A comment must engage with documentation quality,
   coverage, or findability to be `doc_relevant`. A mention of the word "docs" in
   passing is not enough. (This strictness is why the LLM keeps 375 records where
   the lexicon's looser gate keeps 1038.)
6. **Multi-label honestly.** Assign every aspect/feeling actually present; assign
   none if none is present rather than forcing a guess.

## Auditing the labels

`data/labeled_llm/<run>.jsonl` stores judgments keyed by record id only. To make
every label reviewable without the gitignored normalized data, run:

```sh
python scripts/audit_llm.py            # latest run
python scripts/audit_llm.py <run_id>   # a specific snapshot
```

This writes `data/labeled_llm/<run>.audit.jsonl` — one row per record with the
verbatim `text`, `title`, and `url` **next to** the LLM's `doc_relevant`,
`aspects`, `feelings`, `expectation`, and `polarity`. That file is committed, so
anyone can audit *why* a record was labeled the way it was, from a fresh clone,
offline. (Regenerating it requires the normalized snapshot on disk; re-run
`collect` for the run id if it has been pruned.)

## Known residuals

- **Non-reproducible.** Re-running gives different numbers. Do not diff two LLM
  runs as a trend; diff the lexicon runs and use the LLM only as a periodic
  sanity check.
- **Same corpus bias.** Both instruments read a complaint-skewed sample (people
  post about docs when annoyed), so absolute negativity is inflated for both.
  The *method-vs-method* comparison controls for this; the absolute LLM negativity
  does not.
- **Small per-aspect samples.** After the strict relevance gate, some aspects
  have few records (e.g. `search` 17, `examples` 34, `accuracy` 39). Their
  percentages are noisy; read them as "worth investigating," not settled.
