"""
Follow-up drafting + (conditional) sending.

- draft_email(): a short, tailored follow-up email for an application.
- draft_linkedin(): a short LinkedIn note + who to message (manual send only).
- process_followups(): find due follow-ups, draft them, optionally auto-send
  the EMAIL when a real contact email is present and auto-send is enabled, and
  return a summary block for the digest. LinkedIn is never auto-sent.

Safety boundaries (deliberate):
  - We never guess/scrape an individual's private email. We only auto-send to a
    contact_email that was explicitly provided (from the posting or your sheet).
  - LinkedIn messaging is always manual. We output the person/role to contact
    and a drafted note; you send it yourself.
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText
from typing import List, Tuple

import config
from applications import Application, ApplicationStore

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _log(msg: str) -> None:
    print(f"[followup] {msg}", file=sys.stderr)


def draft_email(app: Application) -> Tuple[str, str]:
    """Return (subject, body) for a follow-up email."""
    name = config.APPLICANT_NAME
    greeting = f"Hi {app.contact_name}," if app.contact_name else "Hello,"
    role = app.role or "the role"
    company = app.company or "your team"
    subject = f"Following up — {role} application ({name})"
    body = (
        f"{greeting}\n\n"
        f"I recently applied for {role} at {company} and wanted to follow up "
        f"to reiterate my interest. I'm a CS master's student at CU Boulder "
        f"with experience building backend, cloud, and ML systems, and the "
        f"role stood out as a strong fit for what I've been working on.\n\n"
        f"I'd welcome the chance to share how my background could contribute, "
        f"and I'm happy to provide anything helpful for your review.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{name}\n{config.APPLICANT_CONTACT_LINE}"
    )
    return subject, body


def draft_linkedin(app: Application) -> str:
    """Short LinkedIn note (<= ~300 chars) for manual sending."""
    role = app.role or "the role"
    company = app.company or "your team"
    name = config.APPLICANT_NAME
    return (
        f"Hi — I recently applied for {role} at {company} and wanted to connect. "
        f"I'm a CS master's student at CU Boulder focused on backend/cloud/ML "
        f"engineering and I'm genuinely excited about {company}. Would love to "
        f"briefly share why I think I'd be a strong fit. Thanks! — {name}"
    )


def _who_to_message(app: Application) -> str:
    if app.contact_name:
        who = app.contact_name
        if app.linkedin_hint:
            who += f" ({app.linkedin_hint})"
        return who
    if app.linkedin_hint:
        return app.linkedin_hint
    return (f"Search LinkedIn: \"{app.company} recruiter\" or "
            f"\"{app.company} university recruiting\" / the hiring team for "
            f"{app.role}")


def _send_email(to_addr: str, subject: str, body: str) -> bool:
    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not user or not pw:
        _log("auto-send skipped: GMAIL creds not set")
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(user, [to_addr], msg.as_string())
        _log(f"follow-up email sent to {to_addr}")
        return True
    except (smtplib.SMTPException, OSError) as e:
        _log(f"follow-up send failed: {e}")
        return False


def process_followups(store: ApplicationStore, auto_send: bool) -> str:
    """Draft (and optionally send) due follow-ups. Returns a digest text block.

    Mutates store (marks sent). Caller is responsible for store.save().
    """
    due = store.due_followups()
    if not due:
        return ""

    lines = [f"\n=== FOLLOW-UPS DUE ({len(due)}) ===",
             f"(auto-send email: {'ON' if auto_send else 'OFF — draft only'})\n"]

    for app in due:
        subject, body = draft_email(app)
        li_note = draft_linkedin(app)
        who = _who_to_message(app)

        lines.append(f"* {app.company} — {app.role}")
        lines.append(f"  applied: {app.date_applied}  |  {app.url}")

        can_autosend = bool(app.contact_email) and auto_send
        if can_autosend:
            ok = _send_email(app.contact_email, subject, body)
            if ok:
                store.mark_followed_up(app)
                lines.append(f"  EMAIL: auto-sent to {app.contact_email}")
            else:
                lines.append(f"  EMAIL: auto-send FAILED — draft below, send manually")
                lines.append(f"    To: {app.contact_email or '(no contact email)'}")
                lines.append(f"    Subject: {subject}")
                lines.append(f"    {body.splitlines()[0]} ...")
        else:
            to = app.contact_email or "(no contact email on file — send yourself)"
            lines.append(f"  EMAIL (draft — send yourself): To: {to}")
            lines.append(f"    Subject: {subject}")
            lines.append("    " + body.replace("\n", "\n    "))

        lines.append(f"  LINKEDIN (manual): message -> {who}")
        lines.append(f"    Note: {li_note}")
        lines.append("")

    return "\n".join(lines)
