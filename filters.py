"""
Filtering, dedup, and seen-history.

Pipeline (applied in main):
  1. filter_jobs()  -> keep only entry-level, on-topic, non-hardware, recent
  2. dedup()        -> collapse duplicates within this run
  3. SeenStore      -> drop jobs emailed on a previous run; record new ones
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Set

import config
from job import Job


def _log(msg: str) -> None:
    print(f"[filters] {msg}", file=sys.stderr)


def _any_in(text: str, terms: Iterable[str]) -> bool:
    return any(t in text for t in terms)


def _is_curated_repo(job: Job) -> bool:
    """SimplifyJobs + the extra GitHub repos: curated lists with age markers."""
    return job.source == "simplify-newgrad" or job.source.startswith("github-")


def is_entry_level(job: Job) -> bool:
    title = job.title.lower()
    # Explicit senior markers disqualify.
    if _any_in(title, config.SENIOR_TITLE_TERMS):
        return False
    # Curated repos are already new-grad/early-career.
    if _is_curated_repo(job):
        return True
    # Early-career if the TITLE says so, or the DESCRIPTION indicates ~0-1 yrs.
    if _any_in(title, config.NEW_GRAD_TITLE_TERMS):
        return True
    desc = job.description.lower()
    return _any_in(desc, config.EARLY_CAREER_DESC_TERMS)


def requires_citizenship(job: Job) -> bool:
    """True if the role requires US citizenship or a clearance implying it."""
    # SimplifyJobs marks these with a flag captured in extra['citizenship'].
    if job.extra.get("citizenship"):
        return True
    return _any_in(job.haystack(), config.CITIZENSHIP_EXCLUDE_TERMS)


def no_sponsorship(job: Job) -> bool:
    """True if the role explicitly won't sponsor / isn't open to F1/J1.

    Only matches NEGATIVE phrasings, so a role advertising that it DOES
    sponsor is not dropped.
    """
    return _any_in(job.haystack(), config.NO_SPONSORSHIP_EXCLUDE_TERMS)


def is_on_topic(job: Job) -> bool:
    hay = job.haystack()
    if _any_in(hay, config.GLOBAL_EXCLUDE_TERMS):
        return False
    if _any_in(hay, config.HARDWARE_EXCLUDE_TERMS):
        return False
    if requires_citizenship(job):
        return False
    if no_sponsorship(job):
        return False
    return _any_in(hay, config.TARGET_KEYWORDS)


def location_ok(job: Job) -> bool:
    if not config.PREFERRED_LOCATION_TERMS:
        return True
    loc = job.location.lower().strip()
    if not loc:
        return config.KEEP_UNKNOWN_LOCATION
    return _any_in(loc, config.PREFERRED_LOCATION_TERMS)


def timing_ok(job: Job) -> bool:
    """Keep roles for the target season (Summer 2027) or with no season stated.

    Rule:
      - If a TARGET season/year term appears -> KEEP.
      - Else if a PAST season/year term appears -> DROP (too early).
      - Else (no season/year mentioned) -> KEEP.
    """
    hay = job.haystack()
    if _any_in(hay, config.TARGET_SEASON_TERMS):
        return True
    if _any_in(hay, config.PAST_SEASON_TERMS):
        return False
    return True


def _simplify_recent(job: Job, now: "datetime | None" = None) -> bool:
    # If an absolute date was parsed into posted_at, use it directly.
    if job.posted_at is not None:
        now = now or datetime.now(timezone.utc)
        return job.posted_at >= now - timedelta(days=config.SIMPLIFY_MAX_AGE_DAYS)
    age = (job.extra.get("age") or "").lower().strip()
    if not age:
        return False
    if age.endswith(("h", "m")) or age in ("today",):
        return True
    if age.endswith("d"):
        try:
            return int(age[:-1]) <= config.SIMPLIFY_MAX_AGE_DAYS
        except ValueError:
            return False
    return False


def is_recent(job: Job, now: "datetime | None" = None) -> bool:
    """Whether a job passes the recency gate.

    Behavior depends on config.RECENCY_MODE:

    - "strict": keep only jobs within LOOKBACK_HOURS (by timestamp, or by the
      SimplifyJobs age marker). ATS timestamps are unreliable, so this is
      accurate but often nearly empty.

    - "new_to_you": SimplifyJobs still uses its age marker. For everything else
      (ATS/YC boards) the clock is NOT used here -- the seen-history in main.py
      decides novelty. We only drop jobs with a real timestamp older than
      NEW_TO_YOU_MAX_AGE_DAYS so the initial backlog isn't ancient.
    """
    now = now or datetime.now(timezone.utc)

    if _is_curated_repo(job):
        return _simplify_recent(job)

    if config.RECENCY_MODE == "new_to_you":
        if job.posted_at is not None:
            oldest = now - timedelta(days=config.NEW_TO_YOU_MAX_AGE_DAYS)
            return job.posted_at >= oldest
        return True  # no timestamp -> let seen-history gate it

    # strict mode
    cutoff = now - timedelta(hours=config.LOOKBACK_HOURS)
    if job.posted_at is not None:
        return job.posted_at >= cutoff
    return False


def freshness_seconds(job: Job, now: "datetime | None" = None) -> float:
    """Approximate age of a job in seconds. Smaller = fresher.

    Uses posted_at when present; otherwise parses the SimplifyJobs age marker
    ("45m", "8h", "2d"). Unknown ages sort to the end.
    """
    now = now or datetime.now(timezone.utc)
    if job.posted_at is not None:
        return max(0.0, (now - job.posted_at).total_seconds())
    age = (job.extra.get("age") or "").lower().strip()
    if age.endswith("m") and age[:-1].isdigit():
        return int(age[:-1]) * 60
    if age.endswith("h") and age[:-1].isdigit():
        return int(age[:-1]) * 3600
    if age.endswith("d") and age[:-1].isdigit():
        return int(age[:-1]) * 86400
    if age in ("today",):
        return 0.0
    return float("inf")  # unknown -> last


def filter_jobs(jobs: List[Job]) -> List[Job]:
    now = datetime.now(timezone.utc)
    kept: List[Job] = []
    counts = {"entry": 0, "topic": 0, "loc": 0, "timing": 0, "recent": 0}
    for j in jobs:
        if not is_entry_level(j):
            continue
        counts["entry"] += 1
        if not is_on_topic(j):
            continue
        counts["topic"] += 1
        if not location_ok(j):
            continue
        counts["loc"] += 1
        if not timing_ok(j):
            continue
        counts["timing"] += 1
        if not is_recent(j, now):
            continue
        counts["recent"] += 1
        kept.append(j)
    _log(
        f"filter funnel -> entry:{counts['entry']} topic:{counts['topic']} "
        f"loc:{counts['loc']} timing:{counts['timing']} recent:{counts['recent']}"
    )
    return kept


def dedup(jobs: List[Job]) -> List[Job]:
    seen: Set[str] = set()
    out: List[Job] = []
    for j in jobs:
        k = j.dedup_key
        if k in seen:
            continue
        seen.add(k)
        out.append(j)
    if len(out) != len(jobs):
        _log(f"dedup: {len(jobs)} -> {len(out)}")
    return out


class SeenStore:
    """Persists dedup keys already emailed so you never get the same job twice.

    Stored as JSON: {key: iso_timestamp}. Entries older than `ttl_days` are
    pruned so the file doesn't grow forever.
    """

    def __init__(self, path: str = "seen.json", ttl_days: int = 30):
        self.path = path
        self.ttl_days = ttl_days
        self.data: dict = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (ValueError, OSError) as e:
                _log(f"seen-store load failed ({e}); starting fresh")
                self.data = {}
        self._prune()

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)
        fresh = {}
        for k, v in self.data.items():
            try:
                if datetime.fromisoformat(v) >= cutoff:
                    fresh[k] = v
            except (ValueError, TypeError):
                continue
        self.data = fresh

    def filter_new(self, jobs: List[Job]) -> List[Job]:
        return [j for j in jobs if j.dedup_key not in self.data]

    def record(self, jobs: List[Job]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for j in jobs:
            self.data[j.dedup_key] = now

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=0)
        except OSError as e:
            _log(f"seen-store save failed: {e}")
