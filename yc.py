"""
Y Combinator source.

Two-phase design so runs stay fast:

  1. DISCOVERY (occasional): pull YC's public `hiring.json`, keep software/AI
     companies, and probe each one's slug against Greenhouse/Lever/Ashby to
     find a public job board. Cache the resolved boards to `yc_boards.json`.

  2. FETCH (every run): read `yc_boards.json` and pull jobs from the cached
     boards using the same public ATS APIs.

Run discovery manually or on a schedule:
    python yc.py --discover           # refresh yc_boards.json
    python yc.py --discover --limit 300

Data source: yc-oss/api (https://github.com/yc-oss/api), an unofficial public
JSON API of YC companies built from YC's Algolia index. Content was rephrased
for compliance with licensing restrictions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List, Optional

import requests

import config
from job import Job
from sources import (
    fetch_greenhouse,
    fetch_lever,
    fetch_ashby,
    _parse_dt,  # reused for consistency
)

YC_HIRING_URL = "https://yc-oss.github.io/api/companies/hiring.json"
YC_BOARDS_CACHE = "yc_boards.json"

# Industry/tag signals for keeping vs dropping YC companies at discovery time.
_SW_SIGNALS = (
    "saas", "developer tools", "developer-tools", "ai", "artificial intelligence",
    "fintech", "b2b", "data", "infrastructure", "machine learning", "devops",
    "security", "api", "analytics", "cloud", "open source", "engineering",
    "productivity", "software",
)
_HW_SIGNALS = (
    "robotics", "manufacturing", "biotech", "hard tech", "hardware",
    "semiconductor", "medical devices", "aerospace", "drones",
)


def _log(msg: str) -> None:
    print(f"[yc] {msg}", file=sys.stderr)


def _is_relevant(company: dict) -> bool:
    tags = " ".join(t.lower() for t in company.get("tags", []))
    industry = (company.get("industry") or "").lower()
    sub = (company.get("subindustry") or "").lower()
    blob = f"{tags} {industry} {sub}"
    if any(h in blob for h in _HW_SIGNALS):
        return False
    return any(s in blob for s in _SW_SIGNALS)


def _slug_candidates(company: dict) -> List[str]:
    slug = (company.get("slug") or "").strip().lower()
    name = (company.get("name") or "").strip().lower()
    cands = []
    for c in (slug, slug.replace("-", ""), re.sub(r"[^a-z0-9]", "", name)):
        if c and c not in cands:
            cands.append(c)
    return cands


def _probe_board(session: requests.Session, slug: str) -> Optional[str]:
    """Return 'greenhouse'|'lever'|'ashby' if slug resolves, else None."""
    try:
        if session.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=8,
        ).status_code == 200:
            return "greenhouse"
        if session.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=8
        ).status_code == 200:
            return "lever"
        if session.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=8
        ).status_code == 200:
            return "ashby"
    except requests.RequestException:
        return None
    return None


def discover(limit: int = 400) -> Dict[str, List[str]]:
    """Build {ats: [slug, ...]} from YC hiring companies. Writes the cache."""
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    try:
        companies = s.get(YC_HIRING_URL, timeout=config.REQUEST_TIMEOUT).json()
    except (requests.RequestException, ValueError) as e:
        _log(f"discover: failed to fetch hiring list: {e}")
        return {}

    relevant = [c for c in companies if _is_relevant(c)]
    # Prioritize top companies + larger teams (more likely to have real boards).
    relevant.sort(
        key=lambda c: (c.get("top_company", False), c.get("team_size") or 0),
        reverse=True,
    )
    relevant = relevant[:limit]
    _log(f"discover: {len(companies)} hiring, {len(relevant)} relevant probed")

    boards: Dict[str, List[str]] = {"greenhouse": [], "lever": [], "ashby": []}
    resolved = 0
    for c in relevant:
        for slug in _slug_candidates(c):
            ats = _probe_board(s, slug)
            if ats:
                if slug not in boards[ats]:
                    boards[ats].append(slug)
                    resolved += 1
                break
        time.sleep(0.02)  # be polite

    with open(YC_BOARDS_CACHE, "w", encoding="utf-8") as f:
        json.dump(boards, f, indent=2)
    _log(f"discover: resolved {resolved} boards -> {YC_BOARDS_CACHE} "
         f"(gh:{len(boards['greenhouse'])} lv:{len(boards['lever'])} "
         f"ash:{len(boards['ashby'])})")
    return boards


def _load_cache() -> Dict[str, List[str]]:
    if not os.path.exists(YC_BOARDS_CACHE):
        _log(f"no {YC_BOARDS_CACHE}; run 'python yc.py --discover' first")
        return {"greenhouse": [], "lever": [], "ashby": []}
    try:
        with open(YC_BOARDS_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError) as e:
        _log(f"cache load failed: {e}")
        return {"greenhouse": [], "lever": [], "ashby": []}


def fetch_yc() -> List[Job]:
    """Fetch jobs from cached YC boards. Tags each job's source as yc-*."""
    boards = _load_cache()
    jobs: List[Job] = []
    gh = fetch_greenhouse(boards.get("greenhouse", []))
    lv = fetch_lever(boards.get("lever", []))
    ash = fetch_ashby(boards.get("ashby", []))
    for j in gh + lv + ash:
        j.source = "yc-" + j.source  # e.g. yc-greenhouse
        j.extra["yc"] = True
        jobs.append(j)
    _log(f"yc: {len(jobs)} raw jobs from cached boards")
    return jobs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="YC source discovery/fetch")
    ap.add_argument("--discover", action="store_true",
                    help="refresh yc_boards.json by probing YC hiring companies")
    ap.add_argument("--limit", type=int, default=400,
                    help="max YC companies to probe during discovery")
    args = ap.parse_args()
    if args.discover:
        discover(limit=args.limit)
    else:
        jobs = fetch_yc()
        for j in jobs[:20]:
            print(f"{j.source} | {j.company} | {j.title} | {j.location}")
