# New Grad Tech Job Digest

Automatically finds **new-grad / entry-level** roles in software engineering,
cloud, data engineering, ML/AI, and backend (light hardware OK, pure hardware
excluded), posted in the **last 24 hours**, and emails you a clean digest
**twice a day** — all running for free on **GitHub Actions**.

## How it works

```
sources (APIs) ──▶ filter (24h + role + keywords) ──▶ dedup ──▶
   drop already-seen ──▶ email digest ──▶ record seen-history
```

Sources pulled every run:

| Source | Type | Auth |
| --- | --- | --- |
| Greenhouse | Public JSON board API | none |
| Lever | Public JSON postings API | none |
| Ashby | Public posting API | none |
| RemoteOK | Public JSON feed | none |
| SimplifyJobs New-Grad repo | Parsed README (HTML table) | none |
| Y Combinator | yc-oss public API + ATS auto-discovery | none |
| USAJobs | Official government API | free API key |

### Y Combinator source

Uses the public [yc-oss/api](https://github.com/yc-oss/api) to list YC
companies that are currently hiring, filters to software/AI companies (drops
pure hardware/biotech), then auto-discovers each company's public job board on
Greenhouse/Lever/Ashby. Resolved boards are cached in `yc_boards.json`.

```bash
python yc.py --discover            # refresh the cache (probes ~400 companies)
python yc.py --discover --limit 600
python yc.py                       # print a sample from the cache
```

The GitHub Actions workflow refreshes this cache automatically every Monday.
The last discovery resolved ~220 YC boards (hundreds of startup roles).

All fetches fail gracefully: if one source is down, the run still completes
with the others.

## Files

- `config.py` — everything you tune: keywords, role terms, hardware excludes,
  location preferences, company lists, lookback window, recipient email.
- `sources.py` — one fetcher per source, each returns normalized `Job`s.
- `filters.py` — 24h recency, entry-level/keyword/hardware filtering, dedup,
  and the `seen.json` history that prevents repeat emails.
- `emailer.py` — builds the HTML + plain-text digest and sends via Gmail SMTP.
- `main.py` — the entrypoint that ties it together.
- `.github/workflows/job-digest.yml` — the twice-daily schedule.
- `seen.json` — auto-created history of jobs already emailed (committed back
  by the workflow so it persists between runs). Do not delete.

## Setup

### 1. Push this to a GitHub repo

```bash
git init
git add .
git commit -m "feat: new-grad job digest"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 2. Create a Gmail App Password (for sending email)

1. Turn on **2-Step Verification** on the Google account you'll send from:
   <https://myaccount.google.com/security>
2. Create an App Password: <https://myaccount.google.com/apppasswords>
   (pick "Mail" / "Other"). You'll get a 16-character password.

You can send from any Gmail account; the digest is always delivered to
`krutis1972@gmail.com` (set in `config.py`).

### 3. (Optional) Get a free USAJobs API key

Only needed if you want federal jobs. Request one here:
<https://developer.usajobs.gov/apirequest/> — it arrives by email. Without it,
the USAJobs source is simply skipped.

### 4. Add GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | Required |
| --- | --- | --- |
| `GMAIL_USER` | the sending Gmail address | yes |
| `GMAIL_APP_PASSWORD` | the 16-char app password | yes |
| `USAJOBS_API_KEY` | your USAJobs key | optional |
| `USAJOBS_EMAIL` | the email you registered with USAJobs | optional |

### 5. Done

The workflow runs automatically on schedule. To test immediately:
repo → **Actions → Job Digest → Run workflow**.

## Schedule (timezone note)

GitHub Actions cron is always **UTC** and does not follow daylight saving.
Configured for **Mountain Daylight Time** (Denver, most of the year):

| Cron (UTC) | MDT (summer) | MST (winter) |
| --- | --- | --- |
| `0 13 * * *` | 7:00 AM | 6:00 AM |
| `0 0 * * *` | 6:00 PM | 5:00 PM |

The 1-hour winter drift is harmless: the 24h window + `seen.json` mean you
never miss a job or get a duplicate. To lock exact local times year-round,
edit the two `cron:` lines in `.github/workflows/job-digest.yml` at each DST
change.

Recruiting data suggests most US roles post Tue–Thu, early morning, and
applying within ~24–48h helps — which is exactly what the morning run targets.

## Run it locally

```bash
python -m pip install -r requirements.txt

# Dry run: never sends email, prints the digest, ignores history
python main.py --dry-run --no-seen

# Real run (needs env vars set)
$env:GMAIL_USER="you@gmail.com"
$env:GMAIL_APP_PASSWORD="your16charapppw"
python main.py --label morning
```

Flags:
- `--dry-run` — print the digest instead of emailing.
- `--no-seen` — ignore and don't update `seen.json` (useful for testing).
- `--label morning|evening|...` — label shown in the email subject/body.

## Tuning

Everything is in `config.py`:

- **More companies** — add board/company slugs to `GREENHOUSE_BOARDS`,
  `LEVER_COMPANIES`, `ASHBY_COMPANIES`. A wrong slug just logs a 404 and is
  skipped, so it's safe to experiment.
- **Different roles/keywords** — edit `TARGET_KEYWORDS`, `NEW_GRAD_TITLE_TERMS`,
  `SENIOR_TITLE_TERMS`.
- **Location** — edit `PREFERRED_LOCATION_TERMS`, or set it to `[]` to keep
  every location. Remote is always kept.
- **Window** — change `LOOKBACK_HOURS` (default 24).
- **Too much / too little** — if you get too few, widen keywords or add
  companies; too many, tighten `SENIOR_TITLE_TERMS` or location.

## Recency: "new to you" vs "strict"

ATS boards (Greenhouse/Lever/Ashby/YC) don't expose a reliable "posted" date —
their timestamp reflects the last board sync. So a strict 24h clock throws away
almost everything. `config.RECENCY_MODE` controls this:

- `"new_to_you"` (default) — email any matching role you **haven't been shown
  before**, tracked in `seen.json`. Your **first email is a backlog** of all
  current matches (~30-150 roles); every run after only shows genuinely new
  ones. No repeats, nothing missed. SimplifyJobs still uses its reliable age
  markers, and truly ancient postings (> `NEW_TO_YOU_MAX_AGE_DAYS`) are dropped.
- `"strict"` — only jobs within `LOOKBACK_HOURS`. Accurate but usually
  near-empty because of the timestamp issue above.

Because the first `new_to_you` run is a backlog, expect a big first email, then
small daily ones.

## Notes

- Uses only official/public APIs and public GitHub repos — no ToS-violating
  scraping of LinkedIn/Indeed.
- A run that finds **zero** new jobs sends **no email** (avoids noise).
- Filters out roles requiring **US citizenship** or an active security
  clearance (see `CITIZENSHIP_EXCLUDE_TERMS` in `config.py`).
- Matches **early-career / 0-1 yr** roles, not just new-grad titles.
- Email is grouped by **Today / Yesterday / Earlier**, freshest first.
