"""
Entrypoint.

Digest (default):
  python main.py                 # fetch -> filter -> email digest (+ follow-ups)
  python main.py --label morning # set the digest label
  python main.py --dry-run       # never send; print digest
  python main.py --no-seen       # ignore + don't update seen.json

Application tracking:
  python main.py add --company X --role Y --url Z [--date 2026-09-28] \
        [--email recruiter@x.com] [--contact "Jane Doe"] [--resume ml]
  python main.py import path/to/your_applications.csv   # merge a sheet
  python main.py followups [--send]   # show/send due follow-ups now
"""
from __future__ import annotations

import argparse
import sys

import env_loader
env_loader.load_env()  # populate GMAIL_* from .env before anything reads them

import emailer
import filters
import sources


def _log(msg: str) -> None:
    print(f"[main] {msg}", file=sys.stderr)


def run_digest(label: str, dry_run: bool, use_seen: bool) -> int:
    raw = sources.fetch_all()
    filtered = filters.filter_jobs(raw)
    deduped = filters.dedup(filtered)

    store = None
    if use_seen:
        store = filters.SeenStore()
        fresh = store.filter_new(deduped)
        _log(f"seen-store: {len(deduped)} -> {len(fresh)} after removing already-emailed")
    else:
        fresh = deduped

    fresh.sort(key=filters.freshness_seconds)
    _log(f"final job count: {len(fresh)}")

    # Optional per-email cap: email the top-N freshest; the rest stay unseen
    # and roll into the next run (so volume spreads across runs/days).
    import config
    overflow = 0
    to_email = fresh
    if config.MAX_JOBS_PER_EMAIL and len(fresh) > config.MAX_JOBS_PER_EMAIL:
        overflow = len(fresh) - config.MAX_JOBS_PER_EMAIL
        to_email = fresh[:config.MAX_JOBS_PER_EMAIL]
        _log(f"capping email at {config.MAX_JOBS_PER_EMAIL}; "
             f"{overflow} roll to next run")

    # Build the follow-up block (drafts due follow-ups; may auto-send email).
    from applications import ApplicationStore
    import followup
    app_store = ApplicationStore()
    auto_send = config.FOLLOWUP_AUTO_SEND_EMAIL and not dry_run
    followup_block = followup.process_followups(app_store, auto_send=auto_send)
    if followup_block:
        _log("appended follow-up section to digest")

    if not to_email and not followup_block:
        _log("no new jobs and no follow-ups; nothing to send")
        if store:
            store.save()
        app_store.save()
        return 0

    label2 = label if not overflow else f"{label}, +{overflow} queued"
    sent = emailer.send_digest(to_email, run_label=label2,
                               extra_section=followup_block)

    # Save the emailed jobs so you can review (applied/skip) them later.
    if to_email and (sent or dry_run):
        try:
            import review_queue
            review_queue.save_queue(to_email)
        except Exception as e:
            _log(f"could not save review queue: {e}")

    # Record ONLY the emailed jobs as seen, so overflow re-appears next run.
    if store and (sent or dry_run):
        store.record(to_email)
    if store:
        store.save()
    app_store.save()
    return 0


def run_add(args) -> int:
    from applications import Application, ApplicationStore
    store = ApplicationStore()
    app = Application(
        company=args.company or "", role=args.role or "", url=args.url or "",
        source=args.source or "manual", date_applied=args.date or "",
        contact_email=args.email or "", contact_name=args.contact or "",
        linkedin_hint=args.linkedin or "", resume_variant=args.resume or "",
        notes=args.notes or "",
    )
    added = store.add(app)
    store.save()
    print("added" if added else "already logged (duplicate)")
    return 0


def run_import(args) -> int:
    from applications import ApplicationStore
    store = ApplicationStore()
    n = store.import_csv(args.csv_path)
    store.save()
    print(f"imported {n} new applications")
    return 0


def run_inbox(args) -> int:
    from applications import ApplicationStore
    store = ApplicationStore()
    n = store.import_inbox(args.path or "applied_inbox.txt")
    store.save()
    print(f"inbox: logged {n} new applications")
    return 0


def run_followups(args) -> int:
    import config
    from applications import ApplicationStore
    import followup
    store = ApplicationStore()
    block = followup.process_followups(
        store, auto_send=(args.send and config.FOLLOWUP_AUTO_SEND_EMAIL)
    )
    store.save()
    if not block:
        print("No follow-ups due.")
        return 0
    if args.email:
        # Send a standalone follow-ups email (reminders even on no-jobs days).
        sent = emailer.send_followups_email(block)
        print("emailed follow-ups" if sent else block)
    else:
        print(block)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Job digest + application tracker")
    sub = ap.add_subparsers(dest="cmd")

    # digest flags live on the top-level parser (default command)
    ap.add_argument("--label", default="digest")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-seen", action="store_true")

    p_add = sub.add_parser("add", help="log an application")
    for f in ("company", "role", "url", "source", "date", "email",
              "contact", "linkedin", "resume", "notes"):
        p_add.add_argument(f"--{f}")

    p_imp = sub.add_parser("import", help="merge a CSV of applications")
    p_imp.add_argument("csv_path")

    p_inbox = sub.add_parser("inbox",
                             help="log jobs from applied_inbox.txt (free-form)")
    p_inbox.add_argument("path", nargs="?", default="applied_inbox.txt")

    p_fu = sub.add_parser("followups", help="show/send due follow-ups")
    p_fu.add_argument("--send", action="store_true",
                      help="auto-send follow-up emails (only if enabled in config)")
    p_fu.add_argument("--email", action="store_true",
                      help="email the follow-ups reminder digest to yourself")

    sub.add_parser("testmail", help="send a test email to verify SMTP creds")
    sub.add_parser("review", help="mark emailed jobs applied/skip interactively")

    args = ap.parse_args()

    if args.cmd == "add":
        return run_add(args)
    if args.cmd == "import":
        return run_import(args)
    if args.cmd == "inbox":
        return run_inbox(args)
    if args.cmd == "followups":
        return run_followups(args)
    if args.cmd == "testmail":
        return emailer.send_test_email()
    if args.cmd == "review":
        import review_queue
        return review_queue.run_review()

    # default: digest
    if args.dry_run:
        import os
        os.environ.pop("GMAIL_USER", None)
        os.environ.pop("GMAIL_APP_PASSWORD", None)
    return run_digest(args.label, args.dry_run, use_seen=not args.no_seen)


if __name__ == "__main__":
    sys.exit(main())
