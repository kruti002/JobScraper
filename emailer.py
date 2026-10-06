"""
Digest formatting + Gmail SMTP delivery.

Auth via env vars (set as GitHub secrets):
  GMAIL_USER      the sending Gmail address (e.g. yourname@gmail.com)
  GMAIL_APP_PASSWORD  16-char Google App Password (needs 2FA enabled)

Recipient is config.EMAIL_TO. If GMAIL_* are missing, delivery is skipped
and the digest is printed to stdout instead (useful for local dry runs).
"""
from __future__ import annotations

import html
import os
import smtplib
import sys
from collections import defaultdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

import config
from job import Job

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _log(msg: str) -> None:
    print(f"[emailer] {msg}", file=sys.stderr)


SOURCE_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "usajobs": "USAJobs",
    "remoteok": "RemoteOK",
    "simplify-newgrad": "SimplifyJobs",
    "yc-greenhouse": "YC (Greenhouse)",
    "yc-lever": "YC (Lever)",
    "yc-ashby": "YC (Ashby)",
    "themuse": "The Muse",
    "remotive": "Remotive",
    "himalayas": "Himalayas",
    "adzuna": "Adzuna",
    "github-vanshb03": "GitHub (vanshb03)",
    "github-speedyapply": "GitHub (speedyapply)",
    "github-jobright": "GitHub (JobRight list)",
    "github-simplify-intern": "GitHub (Simplify Interns)",
}


def _fmt_posted(job: Job) -> str:
    if job.posted_at:
        return job.posted_at.strftime("%b %d, %H:%M UTC")
    age = job.extra.get("age")
    return f"~{age} ago" if age else "recently"


def _resume_for(job: Job) -> str:
    try:
        import resume_match
        return resume_match.best_variant(job)
    except Exception:
        return "SWE"


def _age_days(job: Job) -> float:
    """Job age in days (float). Used for day-bucketing and sorting."""
    import filters
    return filters.freshness_seconds(job) / 86400.0


def _day_bucket(job: Job) -> str:
    d = _age_days(job)
    if d < 1:
        return "Today (last 24h)"
    if d < 2:
        return "Yesterday (24-48h)"
    return "Earlier"


# Order buckets fresh -> old regardless of dict insertion.
_BUCKET_ORDER = ["Today (last 24h)", "Yesterday (24-48h)", "Earlier"]


def _sorted_by_freshness(jobs: List[Job]) -> List[Job]:
    import filters
    return sorted(jobs, key=filters.freshness_seconds)


def build_html(jobs: List[Job], run_label: str) -> str:
    jobs = _sorted_by_freshness(jobs)
    buckets = defaultdict(list)
    for j in jobs:
        buckets[_day_bucket(j)].append(j)

    now = datetime.now(timezone.utc).strftime("%A, %b %d %Y %H:%M UTC")
    parts = [
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "max-width:720px;margin:0 auto;color:#1a1a1a;\">",
        f"<h2 style=\"margin-bottom:2px;\">Early-Career Tech Jobs &mdash; {html.escape(run_label)}</h2>",
        f"<p style=\"color:#666;margin-top:0;font-size:13px;\">Generated {now} &middot; "
        f"{len(jobs)} new role(s), sorted freshest first</p>",
    ]

    for bucket in _BUCKET_ORDER:
        group = buckets.get(bucket)
        if not group:
            continue
        parts.append(
            f"<h3 style=\"margin:18px 0 6px;border-bottom:1px solid #eee;"
            f"padding-bottom:4px;\">{bucket} "
            f"<span style=\"color:#999;font-weight:normal;font-size:13px;\">"
            f"({len(group)})</span></h3>"
        )
        parts.append("<ul style=\"list-style:none;padding:0;margin:0;\">")
        for j in group:
            title = html.escape(j.title)
            company = html.escape(j.company)
            loc = html.escape(j.location) or "Location N/A"
            url = html.escape(j.url, quote=True)
            posted = html.escape(_fmt_posted(j))
            src = html.escape(SOURCE_NAMES.get(j.source, j.source))
            resume = html.escape(_resume_for(j))
            parts.append(
                "<li style=\"margin:0 0 12px;padding:10px 12px;background:#fafafa;"
                "border-radius:8px;\">"
                f"<a href=\"{url}\" style=\"font-weight:600;font-size:15px;"
                f"color:#1a56db;text-decoration:none;\">{title}</a>"
                f"<div style=\"font-size:13px;color:#444;margin-top:2px;\">"
                f"{company} &middot; {loc}</div>"
                f"<div style=\"font-size:12px;color:#888;margin-top:2px;\">"
                f"Posted {posted} &middot; via {src} &middot; "
                f"<b style=\"color:#1a7f37;\">resume: {resume}</b></div>"
                "</li>"
            )
        parts.append("</ul>")

    parts.append(
        "<p style=\"color:#aaa;font-size:11px;margin-top:24px;\">"
        "Automated digest &middot; sources: Greenhouse, Lever, Ashby, USAJobs, "
        "RemoteOK, SimplifyJobs. Tune filters in config.py.</p>"
    )
    parts.append("</div>")
    return "\n".join(parts)


def build_text(jobs: List[Job], run_label: str) -> str:
    jobs = _sorted_by_freshness(jobs)
    buckets = defaultdict(list)
    for j in jobs:
        buckets[_day_bucket(j)].append(j)

    lines = [f"Early-Career Tech Jobs - {run_label}",
             f"{len(jobs)} new role(s), sorted freshest first", ""]
    for bucket in _BUCKET_ORDER:
        group = buckets.get(bucket)
        if not group:
            continue
        lines.append(f"== {bucket} ({len(group)}) ==")
        for j in group:
            src = SOURCE_NAMES.get(j.source, j.source)
            lines.append(f"- {j.title} | {j.company} | {j.location or 'N/A'}")
            lines.append(f"  {j.url}")
            lines.append(f"  posted {_fmt_posted(j)} | via {src} | resume: {_resume_for(j)}")
        lines.append("")
    return "\n".join(lines)


def send_followups_email(block: str) -> bool:
    """Send a standalone follow-ups reminder email. Returns True if sent."""
    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    subject = f"{config.EMAIL_SUBJECT_PREFIX} - follow-ups due"
    if not user or not pw:
        _log("follow-ups email: creds not set, printing instead")
        print(f"\nSUBJECT: {subject}\nTO: {config.EMAIL_TO}\n{block}")
        return False
    html_body = (
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
        "max-width:720px;margin:0 auto;\"><h2>Follow-ups due</h2>"
        "<pre style=\"font-family:ui-monospace,Consolas,monospace;font-size:12px;"
        "white-space:pre-wrap;color:#333;\">" + html.escape(block) + "</pre></div>"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(block, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(user, pw)
            server.sendmail(user, [config.EMAIL_TO], msg.as_string())
        _log(f"sent follow-ups email to {config.EMAIL_TO}")
        return True
    except (smtplib.SMTPException, OSError) as e:
        _log(f"follow-ups email failed: {e}")
        return False


def send_test_email() -> int:
    """Send a tiny test email to verify SMTP credentials. Returns exit code."""
    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not pw:
        print("FAIL: no app password found. Put GMAIL_PASSWORD=... in .env")
        return 1
    if not user:
        print("FAIL: GMAIL_USER (your sending gmail address) is not set.\n"
              "      Add a line to .env, e.g.:  GMAIL_USER=youraddress@gmail.com")
        return 1
    msg = MIMEText(
        "This is a test from your job-digest tool. If you got this, SMTP works.",
        "plain", "utf-8",
    )
    msg["Subject"] = "Job digest — SMTP test"
    msg["From"] = user
    msg["To"] = config.EMAIL_TO
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(user, pw)
            server.sendmail(user, [config.EMAIL_TO], msg.as_string())
        print(f"OK: test email sent from {user} to {config.EMAIL_TO}")
        return 0
    except smtplib.SMTPAuthenticationError:
        print("FAIL: authentication rejected. Check that GMAIL_USER matches the "
              "account the app password was created for, 2FA is on, and the "
              "16-char app password has no spaces.")
        return 1
    except (smtplib.SMTPException, OSError) as e:
        print(f"FAIL: {e}")
        return 1


def send_digest(jobs: List[Job], run_label: str = "digest",
                extra_section: str = "") -> bool:
    """Send the digest email. Returns True if actually sent.

    extra_section: optional plain-text block (e.g. due follow-ups) appended to
    the bottom of the email.
    """
    user = os.environ.get("GMAIL_USER", "").strip()
    app_pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    subject = f"{config.EMAIL_SUBJECT_PREFIX} ({run_label}) - {len(jobs)} new"
    text_body = build_text(jobs, run_label)
    html_body = build_html(jobs, run_label)
    if extra_section:
        text_body += "\n\n" + extra_section
        # Append follow-ups as a <pre> block so formatting survives in HTML.
        html_body += (
            "<hr style=\"margin:24px 0;border:none;border-top:1px solid #eee;\">"
            "<pre style=\"font-family:ui-monospace,Menlo,Consolas,monospace;"
            "font-size:12px;white-space:pre-wrap;color:#333;\">"
            + html.escape(extra_section) + "</pre>"
        )

    if not user or not app_pw:
        _log("GMAIL_USER / GMAIL_APP_PASSWORD not set - printing digest instead")
        print("\n" + "=" * 60)
        print(f"SUBJECT: {subject}")
        print(f"TO: {config.EMAIL_TO}")
        print("=" * 60)
        print(text_body)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(user, app_pw)
            server.sendmail(user, [config.EMAIL_TO], msg.as_string())
        _log(f"sent digest to {config.EMAIL_TO} ({len(jobs)} jobs)")
        return True
    except (smtplib.SMTPException, OSError) as e:
        _log(f"send failed: {e}")
        return False
