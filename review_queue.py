"""
Review queue: lets you mark emailed jobs as applied / skipped from the terminal.

Each digest run saves the jobs it emailed to review_queue.json. Later you run
`python main.py review` and go through them one at a time:

    a = applied   -> logs to applications.csv + starts the 5-day follow-up clock
    s = skip      -> never shown again (added to seen-history)
    enter = later -> leave in the queue
    r = <variant> -> override the resume variant for this one (e.g. "r ml")
    q = quit

The queue stores just enough to recreate an Application row.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from typing import List

QUEUE_FILE = "review_queue.json"


def _log(msg: str) -> None:
    print(f"[review] {msg}", file=sys.stderr)


def save_queue(jobs) -> None:
    """Persist the emailed jobs for later review (newest first already)."""
    import resume_match
    rows = []
    seen_urls = set()
    # Merge with any existing un-reviewed items so nothing is lost.
    existing = _load_raw()
    for r in existing:
        if r.get("url") and r["url"] not in seen_urls:
            rows.append(r)
            seen_urls.add(r["url"])
    for j in jobs:
        if j.url in seen_urls:
            continue
        rows.append({
            "company": j.company,
            "role": j.title,
            "url": j.url,
            "source": j.source,
            "location": j.location,
            "resume_variant": resume_match.best_variant(j),
            "posted": (j.posted_at.isoformat() if j.posted_at
                       else j.extra.get("age", "")),
        })
        seen_urls.add(j.url)
    try:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
    except OSError as e:
        _log(f"save failed: {e}")


def _load_raw() -> List[dict]:
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _write_raw(rows: List[dict]) -> None:
    try:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
    except OSError as e:
        _log(f"save failed: {e}")


def run_review() -> int:
    """Interactive review of queued jobs. Returns exit code."""
    from applications import Application, ApplicationStore

    rows = _load_raw()
    if not rows:
        print("Review queue is empty. Run a digest first.")
        return 0

    app_store = ApplicationStore()
    remaining: List[dict] = []
    applied = skipped = later = 0

    print(f"\n{len(rows)} job(s) to review. "
          f"[a]pplied  [s]kip  [enter]=later  [r <lane>]  [q]uit\n")

    for i, r in enumerate(rows, 1):
        print(f"({i}/{len(rows)}) {r['company']} — {r['role']}")
        print(f"      {r.get('location','')}  |  resume: {r.get('resume_variant','SWE')}")
        print(f"      {r['url']}")
        try:
            choice = input("      > ").strip().lower()
        except EOFError:
            remaining.append(r)
            break

        if choice == "q":
            remaining.append(r)
            remaining.extend(rows[i:])  # keep the rest
            break
        if choice.startswith("r "):
            r["resume_variant"] = choice.split(None, 1)[1].upper()
            print(f"      resume set to {r['resume_variant']}; applied?")
            choice = input("      > ").strip().lower()

        if choice == "a":
            app = Application(
                company=r["company"], role=r["role"], url=r["url"],
                source=r.get("source", ""), date_applied=date.today().isoformat(),
                resume_variant=r.get("resume_variant", ""),
            )
            app_store.add(app)
            applied += 1
            print("      ✓ logged as applied (follow-up in 5 business days)\n")
        elif choice == "s":
            skipped += 1
            print("      ✗ skipped\n")
            # dropping from queue == skipped; also add to seen so it won't
            # resurface in future digests:
            _mark_seen(r["url"])
        else:
            later += 1
            remaining.append(r)
            print("      … kept for later\n")

    app_store.save()
    _write_raw(remaining)
    print(f"Done. applied:{applied}  skipped:{skipped}  later:{later}  "
          f"remaining in queue:{len(remaining)}")
    return 0


def _mark_seen(url: str) -> None:
    """Add a skipped job's key to seen.json so it won't be emailed again."""
    try:
        import filters
        store = filters.SeenStore()
        # Build a throwaway job just to compute the key.
        from job import Job
        j = Job(title="", company="", location="", url=url, source="skip")
        store.data[j.dedup_key] = date.today().isoformat()
        store.save()
    except Exception as e:
        _log(f"could not mark seen: {e}")
