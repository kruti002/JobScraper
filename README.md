# Early-Career Tech Job Digest + Follow-up Tracker

Finds **early-career / new-grad** tech roles (software, cloud, data, ML/AI,
agentic — light hardware OK, pure hardware excluded), tailored to a Summer 2027
target, and emails you a clean digest **every 4 hours**. It also tracks what you
applied to and reminds you to follow up. Runs for free on **GitHub Actions**.

```
sources ─▶ filter (role · keywords · no-citizenship · no-sponsorship · timing · recency)
        ─▶ dedup ─▶ drop already-seen ─▶ email digest (grouped by age, resume-tagged)
        ─▶ record seen-history

applied_inbox.txt ─▶ applications.csv ─▶ follow-up reminders (email + LinkedIn draft)
```

Full rule-by-rule breakdown lives in **[FILTERING_RULES.md](FILTERING_RULES.md)**.

## Sources

| Source | Type | Auth |
| --- | --- | --- |
| Greenhouse / Lever / Ashby | Public ATS APIs (manual company lists) | none |
| Y Combinator | yc-oss API + auto-discovered ATS boards | none |
| SimplifyJobs new-grad repo | Parsed README | none |
| GitHub repos (vanshb03, speedyapply, jobright, Simplify interns) | Parsed READMEs | none |
| The Muse / Remotive / Himalayas / RemoteOK | Public job APIs | none |
| Adzuna | Aggregator API | free key (optional) |
| USAJobs | Federal jobs API | free key (optional) |

Every fetch fails gracefully — if one source is down, the run still completes.

### Y Combinator auto-discovery

Pulls YC companies that are hiring from [yc-oss/api](https://github.com/yc-oss/api),
keeps the software/AI ones, and finds each company's public board on
Greenhouse/Lever/Ashby. Resolved boards are cached in `yc_boards.json` and
refreshed every Monday by the workflow (last run resolved ~370 boards).

```bash
python yc.py --discover            # refresh the cache
python yc.py                       # print a sample from the cache
```

## What gets filtered

A job must pass every stage to reach your inbox (see FILTERING_RULES.md for the
exact term lists):

1. **Early-career** — new-grad / ~0–1 yr; senior titles dropped.
2. **On-topic** — matches a tech keyword; non-tech and **pure-hardware** dropped.
3. **No US-citizenship / clearance** — citizen-only and clearance roles dropped.
4. **No "we don't sponsor"** — roles that exclude F1/J1 or say no visa
   sponsorship are dropped (roles that *do* sponsor are kept).
5. **Location** — US / remote / preferred metros (unknown locations kept).
6. **Timing** — Summer 2027 or no season stated; earlier seasons and
   "immediate hire" roles dropped.
7. **Recency** — curated lists use last ~3 days; ATS/YC boards use "new to you".

The email groups jobs by age (**Last 24h → 1–2 days → 2–3 days → 3–7 days →
older**), freshest first, and tags each with the best-fit **resume variant**
(SWE / Cloud / ML / Data).

## Setup

### 1. Push to a (private) GitHub repo

Make the repo **Private** — it stores your application history.

```bash
git init
git add .
git commit -m "job digest + follow-up tracker"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Before committing, run `git status --short` and confirm **`.env` is NOT listed**
(it's gitignored). `applications.csv` and `applied_inbox.txt` *should* appear —
they're tracked so your state persists across cloud runs.

### 2. Gmail App Password

1. Enable **2-Step Verification**: <https://myaccount.google.com/security>
2. Create an app password: <https://myaccount.google.com/apppasswords> → copy
   the 16-char code (no spaces).

Locally this lives in `.env` (see below). For the cloud, add it as a secret.

### 3. Add GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | Required |
| --- | --- | --- |
| `GMAIL_USER` | sending Gmail address (`krutis1972@gmail.com`) | yes |
| `GMAIL_APP_PASSWORD` | the 16-char app password | yes |
| `USAJOBS_API_KEY` / `USAJOBS_EMAIL` | from developer.usajobs.gov | optional |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | from developer.adzuna.com | optional |

### 4. Turn it on

Repo → **Actions** → enable workflows if prompted → **Job Digest** →
**Run workflow** to fire the first run. The first email is a backlog of all
current matches; after that each run only shows new roles.

## Schedule

Runs every 4 hours (UTC): `0 1,5,9,13,17,21 * * *`. GitHub cron is UTC and
doesn't follow daylight saving; these map to roughly 7am–7pm Denver across the
day. The daily follow-ups email goes out at the 13:00 UTC (morning) run.

Edit the `cron:` line in `.github/workflows/job-digest.yml` to change times.

## Tracking what you applied to

You don't need a local terminal. Keep a running list in **`applied_inbox.txt`**
(edit it right on github.com), one job per line, any of these formats:

```
https://company.com/jobs/123
Stripe - Software Engineer New Grad
Figma | Backend Engineer New Grad | https://figma.com/j/9 | recruiter@figma.com
```

Each scheduled run imports the inbox into `applications.csv`, starts a
**5-business-day follow-up clock**, and clears the inbox. Including a contact
email (the `|` format) lets the follow-up address a real person.

## Follow-ups

5 business days after you applied, the daily follow-up email includes, per role:
- a **drafted follow-up email**, and
- **who to message on LinkedIn** (or a search hint) plus a **drafted note**.

Email auto-send is **off** by default (`FOLLOWUP_AUTO_SEND_EMAIL` in config);
when on, it only sends to a contact email explicitly on file — never a guessed
address. **LinkedIn is always manual** — you send those yourself.

## Local commands (optional)

```bash
python -m pip install -r requirements.txt

python main.py --dry-run --no-seen   # print a digest without sending
python main.py testmail              # verify Gmail SMTP works
python main.py inbox                 # import applied_inbox.txt now
python main.py import sheet.csv      # merge a CSV of applications
python main.py followups             # show due follow-ups (add --email to send)
python main.py review                # interactively mark emailed jobs applied/skip
```

`.env` (local only, gitignored) holds your credentials:

```
GMAIL_USER=krutis1972@gmail.com
GMAIL_PASSWORD=your16charapppw
```

## Files

| File | What | Committed? |
| --- | --- | --- |
| `config.py` | all tunable settings (keywords, filters, sources, timing) | yes |
| `sources.py` | one fetcher per source | yes |
| `filters.py` | all filtering + dedup + seen-history | yes |
| `emailer.py` | builds + sends the digest | yes |
| `applications.py` / `followup.py` | tracking + follow-up drafting | yes |
| `resume_match.py` | best-fit resume variant per job | yes |
| `yc.py` | YC discovery + fetch | yes |
| `main.py` | entrypoint + subcommands | yes |
| `FILTERING_RULES.md` | human-readable rule reference | yes |
| `seen.json` / `yc_boards.json` | run state (auto-managed) | yes |
| `applications.csv` / `applied_inbox.txt` | your application data | yes (private repo) |
| `.env` | your credentials | **no — gitignored** |

## Notes

- Uses only official/public APIs and public GitHub repos — no ToS-violating
  scraping, no auto-applying, no automated LinkedIn messaging.
- A run with **zero** new jobs sends **no email**.
- If this repo ever goes public, re-ignore `applications.csv` and rotate the
  Gmail app password.
