"""Collectors for each source.

Each collector returns ``(raw, records)`` where ``raw`` is the verbatim API
payload (audit trail, written to disk) and ``records`` is a list of normalized
``Record``s. A collector failing (rate limit, block, outage) degrades that one
source: it logs a warning and returns what it has, so a run always completes.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from nixdoc_sentiment.http import Http, HttpError
from nixdoc_sentiment.schema import Record
from nixdoc_sentiment.sources import CollectConfig
from nixdoc_sentiment.store import log
from nixdoc_sentiment.textutil import clean_text


def _epoch_to_iso(epoch) -> str:
    if epoch is None:
        return ""
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# --- Hacker News (Algolia) --------------------------------------------------
def collect_hackernews(http: Http, cfg: CollectConfig) -> tuple[dict, list[Record]]:
    raw: dict = {"hits": []}
    records: list[Record] = []
    seen: set[str] = set()
    for q in cfg.queries_for("hackernews"):
        for page in range(cfg.max_pages):
            url = ("https://hn.algolia.com/api/v1/search_by_date"
                   f"?query={quote_plus(q)}&tags=comment&hitsPerPage=100&page={page}")
            try:
                data = http.get_json(url)
            except HttpError as e:
                log(f"hackernews query {q!r} page {page}: {e}")
                break
            hits = data.get("hits") or []
            if not hits:
                break
            for h in hits:
                oid = str(h.get("objectID"))
                raw["hits"].append(h)
                if oid in seen:
                    continue
                seen.add(oid)
                text = clean_text(h.get("comment_text"))
                if not text:
                    continue
                records.append(Record(
                    id=f"hackernews:{oid}", source="hackernews", native_id=oid,
                    url=f"https://news.ycombinator.com/item?id={oid}",
                    created_utc=h.get("created_at") or "",
                    author=h.get("author"), title=h.get("story_title"),
                    text=text, query=q))
            if page + 1 >= int(data.get("nbPages", 1)):
                break
    return raw, records


# --- NixOS Discourse --------------------------------------------------------
def collect_discourse(http: Http, cfg: CollectConfig) -> tuple[dict, list[Record]]:
    base = "https://discourse.nixos.org"
    raw: dict = {"searches": [], "topics": []}
    records: list[Record] = []
    topic_ids: list[int] = []
    seen_topic: set[int] = set()
    topic_meta: dict[int, dict] = {}

    for q in cfg.queries_for("discourse"):
        for page in range(1, cfg.max_pages + 1):
            url = f"{base}/search.json?q={quote_plus(q)}&page={page}"
            try:
                data = http.get_json(url)
            except HttpError as e:
                log(f"discourse search {q!r} page {page}: {e}")
                break
            raw["searches"].append({"query": q, "page": page, "data": data})
            for t in (data.get("topics") or []):
                topic_meta[t["id"]] = t
            posts = data.get("posts") or []
            if not posts:
                break
            for p in posts:
                tid = p.get("topic_id")
                if tid and tid not in seen_topic:
                    seen_topic.add(tid)
                    topic_ids.append(tid)

    # Fetch full topics (bounded) to get real per-post text, not just blurbs.
    for tid in topic_ids[: cfg.max_topics]:
        try:
            tdata = http.get_json(f"{base}/t/{tid}.json")
        except HttpError as e:
            log(f"discourse topic {tid}: {e}")
            continue
        raw["topics"].append(tdata)
        meta = topic_meta.get(tid, {})
        slug = tdata.get("slug") or meta.get("slug", "")
        title = tdata.get("title") or meta.get("title")
        for post in (tdata.get("post_stream", {}).get("posts") or []):
            pid = post.get("id")
            pn = post.get("post_number")
            text = clean_text(post.get("cooked"))
            if not text:
                continue
            records.append(Record(
                id=f"discourse:{tid}-{pid}", source="discourse",
                native_id=f"{tid}-{pid}",
                url=f"{base}/t/{slug}/{tid}/{pn}",
                created_utc=post.get("created_at") or "",
                author=post.get("username"), title=title, text=text,
                query="topic"))
    return raw, records


# --- GitHub issues (nix.dev etc.) -------------------------------------------
def collect_github(http: Http, cfg: CollectConfig) -> tuple[dict, list[Record]]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        log("github: no GITHUB_TOKEN set -> unauthenticated (low rate limit)")

    raw: dict = {"items": []}
    records: list[Record] = []
    seen: set[str] = set()
    for repo in cfg.github_repos:
        for q in cfg.queries_for("github"):
            for page in range(1, cfg.max_pages + 1):
                query = f"repo:{repo} {q} in:title,body"
                url = ("https://api.github.com/search/issues"
                       f"?q={quote_plus(query)}&per_page=100&page={page}")
                try:
                    data = http.get_json(url, headers=headers)
                except HttpError as e:
                    log(f"github {repo} {q!r} page {page}: {e}")
                    break
                items = data.get("items") or []
                if not items:
                    break
                for it in items:
                    key = str(it.get("id"))
                    raw["items"].append(it)
                    if key in seen:
                        continue
                    seen.add(key)
                    title = it.get("title") or ""
                    body = clean_text(it.get("body"))
                    text = (title + "\n\n" + body).strip() if body else title
                    if not text:
                        continue
                    records.append(Record(
                        id=f"github:{key}", source="github", native_id=key,
                        url=it.get("html_url") or "",
                        created_utc=it.get("created_at") or "",
                        author=(it.get("user") or {}).get("login"),
                        title=title, text=text, query=f"{repo}:{q}"))
                if len(items) < 100:
                    break
    return raw, records


# --- Reddit (r/NixOS) -------------------------------------------------------
def _reddit_token(http: Http) -> tuple[str, dict] | None:
    """Return (base_url, extra_headers) for OAuth if creds present, else None."""
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return None
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    try:
        tok = http.post_form(
            "https://www.reddit.com/api/v1/access_token",
            {"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"})
    except HttpError as e:
        log(f"reddit oauth failed: {e}")
        return None
    access = tok.get("access_token")
    if not access:
        return None
    return "https://oauth.reddit.com", {"Authorization": f"Bearer {access}"}


def collect_reddit(http: Http, cfg: CollectConfig) -> tuple[dict, list[Record]]:
    raw: dict = {"listings": []}
    records: list[Record] = []
    auth = _reddit_token(http)
    if auth:
        base, extra = auth
    else:
        # Public JSON: works from residential IPs; datacenter IPs are often
        # blocked (403). Degrade gracefully in that case.
        base, extra = "https://www.reddit.com", {}
    seen: set[str] = set()
    for q in cfg.queries_for("reddit"):
        url = (f"{base}/r/NixOS/search.json?q={quote_plus(q)}"
               "&restrict_sr=1&sort=new&limit=100&t=all")
        try:
            data = http.get_json(url, headers=extra)
        except HttpError as e:
            log(f"reddit skipped ({q!r}): {e}")
            return raw, records
        raw["listings"].append(data)
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            rid = d.get("id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            title = d.get("title") or ""
            body = clean_text(d.get("selftext"))
            text = (title + "\n\n" + body).strip() if body else title
            if not text:
                continue
            records.append(Record(
                id=f"reddit:{rid}", source="reddit", native_id=rid,
                url="https://www.reddit.com" + (d.get("permalink") or ""),
                created_utc=_epoch_to_iso(d.get("created_utc")),
                author=d.get("author"), title=title, text=text, query=q))
    return raw, records


COLLECTORS = {
    "hackernews": collect_hackernews,
    "discourse": collect_discourse,
    "github": collect_github,
    "reddit": collect_reddit,
}
