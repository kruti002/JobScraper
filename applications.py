"""
Application tracking + follow-up engine.

Stores one row per application in applications.csv (gitignored -- it's your
personal data). Supports:

  - add_application(): log a job you applied to (from this tool or elsewhere)
  - import_csv(): merge a sheet of jobs you applied to outside this tool
  - due_followups(): applications whose 5-business-day follow-up is due
  - mark_followed_up(): record that a follow-up went out

Follow-up policy (see config):
  - FOLLOWUP_BUSINESS_DAYS days after date_applied -> follow-up becomes due.
  - If the application has a real contact_email AND auto-send is enabled, the
    digest can send the drafted email. Otherwise the draft is shown for you to
    send yourself. LinkedIn is always manual: we only tell you who to message.
"""
from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import List, Optional

import config

APPLICATIONS_CSV = "applications.csv"

FIELDNAMES = [
    "company", "role", "url", "source", "date_applied",
    "contact_email", "contact_name", "linkedin_hint",
    "resume_variant", "status", "followup_due", "followup_sent", "notes",
]


def _log(msg: str) -> None:
    print(f"[applications] {msg}", file=sys.stderr)


def _add_business_days(start: date, n: int) -> date:
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            added += 1
    return d


def _parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        from dateutil import parser as dp
        return dp.parse(value).date()
    except Exception:
        return None


@dataclass
class Application:
    company: str = ""
    role: str = ""
    url: str = ""
    source: str = ""
    date_applied: str = ""        # ISO yyyy-mm-dd
    contact_email: str = ""
    contact_name: str = ""
    linkedin_hint: str = ""       # who to message / search hint
    resume_variant: str = ""
    status: str = "applied"       # applied | followed_up | interview | closed
    followup_due: str = ""        # ISO date; computed if blank
    followup_sent: str = ""       # ISO date when follow-up went out
    notes: str = ""

    def key(self) -> str:
        if self.url.strip():
            return self.url.strip().lower()
        return f"{self.company.strip().lower()}::{self.role.strip().lower()}"

    def ensure_followup_due(self) -> None:
        if self.followup_due:
            return
        applied = _parse_date(self.date_applied) or date.today()
        self.followup_due = _add_business_days(
            applied, config.FOLLOWUP_BUSINESS_DAYS
        ).isoformat()


class ApplicationStore:
    def __init__(self, path: str = APPLICATIONS_CSV):
        self.path = path
        self.rows: List[Application] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8", newline="") as f:
                for d in csv.DictReader(f):
                    self.rows.append(Application(**{
                        k: d.get(k, "") or "" for k in FIELDNAMES
                    }))
        except (OSError, TypeError, ValueError) as e:
            _log(f"load failed ({e}); starting empty")
            self.rows = []

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDNAMES)
                w.writeheader()
                for r in self.rows:
                    w.writerow(asdict(r))
        except OSError as e:
            _log(f"save failed: {e}")

    def _index(self) -> dict:
        return {r.key(): r for r in self.rows}

    def add(self, app: Application) -> bool:
        """Add if new (by key). Returns True if added, False if duplicate."""
        if not app.date_applied:
            app.date_applied = date.today().isoformat()
        app.ensure_followup_due()
        idx = self._index()
        if app.key() in idx:
            return False
        self.rows.append(app)
        return True

    def import_csv(self, csv_path: str) -> int:
        """Merge a user-provided sheet of applications. Returns # added.

        Accepts flexible column names (company/Company, role/title/position,
        url/link, date/date_applied/applied).
        """
        if not os.path.exists(csv_path):
            _log(f"import: file not found: {csv_path}")
            return 0
        added = 0
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            for d in csv.DictReader(f):
                low = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in d.items()}
                app = Application(
                    company=low.get("company", ""),
                    role=low.get("role") or low.get("title")
                        or low.get("position", ""),
                    url=low.get("url") or low.get("link", ""),
                    source=low.get("source", "manual-import"),
                    date_applied=(_parse_date(
                        low.get("date_applied") or low.get("date")
                        or low.get("applied", "")) or date.today()).isoformat(),
                    contact_email=low.get("contact_email")
                        or low.get("email", ""),
                    contact_name=low.get("contact_name")
                        or low.get("contact", ""),
                    linkedin_hint=low.get("linkedin_hint")
                        or low.get("linkedin", ""),
                    resume_variant=low.get("resume_variant")
                        or low.get("resume", ""),
                    notes=low.get("notes", ""),
                )
                if not (app.company or app.role or app.url):
                    continue
                if self.add(app):
                    added += 1
        _log(f"import: added {added} new applications from {csv_path}")
        return added

    def import_inbox(self, path: str) -> int:
        """Import a free-form 'applied today' list. Returns # added.

        Each non-empty, non-comment line can be any of:
          https://company.com/jobs/123
          Company - Role
          Company | Role | https://url
          Company | Role | https://url | recruiter@co.com
        Lines starting with # are ignored. After a successful import the file
        is cleared (so the same lines aren't re-added next run); already-logged
        duplicates are skipped either way.
        """
        if not os.path.exists(path):
            return 0
        added = 0
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            company = role = url = email = ""
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                company = parts[0] if len(parts) > 0 else ""
                role = parts[1] if len(parts) > 1 else ""
                url = parts[2] if len(parts) > 2 else ""
                email = parts[3] if len(parts) > 3 else ""
            elif line.lower().startswith("http"):
                url = line
                # derive a readable company from the domain
                try:
                    host = line.split("//", 1)[1].split("/", 1)[0]
                    company = host.replace("www.", "").split(".")[0].title()
                except IndexError:
                    company = "Unknown"
            elif " - " in line:
                company, _, role = line.partition(" - ")
                company, role = company.strip(), role.strip()
            else:
                company = line  # bare company name

            app = Application(
                company=company or "Unknown", role=role, url=url,
                source="applied-inbox",
                date_applied=date.today().isoformat(),
                contact_email=email,
            )
            if not (app.company or app.url):
                continue
            if self.add(app):
                added += 1
        # Clear the inbox so processed lines don't re-import; keep a header.
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Paste jobs you applied to, one per line. Examples:\n"
                        "#   https://company.com/jobs/123\n"
                        "#   Stripe - Software Engineer New Grad\n"
                        "#   Stripe | SWE New Grad | https://... | recruiter@stripe.com\n"
                        "# This file is auto-cleared after each daily import.\n")
        except OSError:
            pass
        _log(f"inbox import: added {added} new applications from {path}")
        return added

    def due_followups(self, today: Optional[date] = None) -> List[Application]:
        today = today or date.today()
        due = []
        for r in self.rows:
            if r.followup_sent:
                continue
            if r.status in ("closed", "interview"):
                continue
            r.ensure_followup_due()
            d = _parse_date(r.followup_due)
            if d and d <= today:
                due.append(r)
        return due

    def mark_followed_up(self, app: Application, when: Optional[date] = None):
        when = when or date.today()
        app.followup_sent = when.isoformat()
        app.status = "followed_up"
