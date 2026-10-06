# Filtering Rules — what the digest keeps and drops

This documents every rule the scraper currently applies, in the order it
applies them. All values live in `config.py`; this file explains what they do.

A job must pass **every** stage below to reach your email. The run log prints
the funnel so you can see where jobs drop:

```
filter funnel -> entry:NNN topic:NNN loc:NNN timing:NNN recent:NNN
```

---

## Pipeline order

```
fetch all sources
  -> is_entry_level   (early-career only)
  -> is_on_topic      (right field, not hardware, not citizenship-locked)
  -> location_ok      (US / remote / preferred metros)
  -> timing_ok        (Summer 2027 or no season stated)
  -> is_recent        (last 2-3 days, or "new to you")
  -> dedup            (collapse duplicates in this run)
  -> seen-history     (drop anything emailed before)
  -> sort freshest first, group by day, tag resume variant
```

---

## 1. Entry-level / early-career (`is_entry_level`)

**Keep** if the role is new-grad or ~0–1 years of experience. **Drop** anything
senior.

- **Dropped** if the title contains a senior marker: senior, sr., staff,
  principal, lead, manager, director, head of, VP, architect, "II/III/IV",
  "L4/L5/L6", "engineer ii/iii", or "5+/6+/7+/8+/10+ years".
- **Kept** automatically if it comes from a curated new-grad list (SimplifyJobs
  or the GitHub repos) — those are pre-vetted as early-career.
- Otherwise **kept** if the **title** says: new grad, entry level, early career,
  university/college grad, recent graduate, graduate/associate engineer,
  junior, "software engineer I/1", "SWE/SDE I/1", campus, apprentice,
  rotational, trainee, emerging talent, "class of 20xx".
- Or **kept** if the **description** signals ~0–1 yrs: "0-1 years", "0-2 years",
  "1-2 years", "no experience required", "recent graduate", etc.

_Tune in: `NEW_GRAD_TITLE_TERMS`, `SENIOR_TITLE_TERMS`, `EARLY_CAREER_DESC_TERMS`._

## 2. On-topic + exclusions (`is_on_topic`)

Checked against the title + location + description.

- **Dropped** if it hits a non-tech term: sales, marketing, recruiter, account
  executive, customer success, nurse, physician, attorney, accountant,
  warehouse, driver, barista, cashier, janitor.
- **Dropped** if it's **pure hardware**: ASIC, VLSI, RTL design, PCB, analog
  design, RF engineer, semiconductor, chip/circuit/hardware design, mechanical
  engineer, electrical engineer, FPGA design, signal integrity, power
  electronics, Cadence, Verilog design. _(Light/embedded software is still
  kept — only pure-hardware roles are dropped.)_
- **Dropped** if it requires **US citizenship / clearance** (see rule 2a).
- **Kept** only if it also matches a target keyword: software, SWE, developer,
  backend, full stack, frontend, cloud, AWS/GCP/Azure, DevOps, SRE, platform,
  infrastructure, distributed, data engineer, ETL, pipeline, analytics, machine
  learning, ML/AI engineer, MLOps, NLP, deep learning, computer vision, LLM,
  Python, Java, C++, Go, TypeScript, React, Node, API, microservice, embedded
  software, firmware.

_Tune in: `GLOBAL_EXCLUDE_TERMS`, `HARDWARE_EXCLUDE_TERMS`, `TARGET_KEYWORDS`._

### 2a. US citizenship / clearance (`requires_citizenship`)

**Dropped** if the posting explicitly requires US citizenship or an active
clearance. Matched phrases include: "US citizenship required", "must be a US
citizen", "citizens only", "active security/secret clearance", "TS/SCI",
"security clearance required", "ability to obtain a security clearance".
SimplifyJobs/GitHub rows flagged with the 🇺🇸 marker are also dropped.

> Note: a role that only says "must be authorized to work in the US" is **kept** —
> that's work authorization, not citizenship.

_Tune in: `CITIZENSHIP_EXCLUDE_TERMS`._

## 3. Location (`location_ok`)

- **Kept** if the location matches a preferred term: remote, United States/USA,
  Colorado, Denver, Boulder, California, Washington, New York, Texas, Seattle,
  San Francisco, Bay Area, Austin, Boston, Chicago, Atlanta, hybrid, anywhere.
- Jobs with **no parseable location** are **kept** (`KEEP_UNKNOWN_LOCATION = True`)
  to favor recall.
- Set `PREFERRED_LOCATION_TERMS = []` to keep every location.

_Tune in: `PREFERRED_LOCATION_TERMS`, `KEEP_UNKNOWN_LOCATION`._

## 4. Timing / target season (`timing_ok`)

Targeting **Summer 2027** (graduation May 2027).

- **Kept** if a target term appears: 2027, summer/winter/spring/fall 2027,
  "2026-2027", "class of 2027".
- **Dropped** if a past term appears and no 2027 term does: 2024, 2025, 2026
  seasons, "class of 2025/2026", "immediate start", "start immediately", "ASAP
  start".
- **Kept** if no season/year is mentioned at all (your rule: "if nothing
  written then it's fine").

_Tune in: `TARGET_SEASON_TERMS`, `PAST_SEASON_TERMS`._

## 5. Recency (`is_recent`) — mode-dependent

Controlled by `RECENCY_MODE` (currently **`new_to_you`**).

- **Curated lists** (SimplifyJobs + GitHub repos): kept if their age marker is
  within `SIMPLIFY_MAX_AGE_DAYS` (currently **3 days**), i.e. "last 2-3 days".
  Absolute dates like "Oct 06" are parsed and checked the same way.
- **ATS / YC boards** (Greenhouse/Lever/Ashby, no reliable post date): the clock
  is **not** used; the seen-history decides novelty. A real timestamp older than
  `NEW_TO_YOU_MAX_AGE_DAYS` (21) is still dropped so the first backlog isn't
  ancient.
- **Aggregators with real dates** (The Muse, Remotive, Himalayas, Adzuna,
  USAJobs): kept if within `LOOKBACK_HOURS` (currently **72h**).

Switch `RECENCY_MODE = "strict"` to require every source be within
`LOOKBACK_HOURS` — accurate but usually near-empty for ATS boards.

_Tune in: `RECENCY_MODE`, `LOOKBACK_HOURS`, `SIMPLIFY_MAX_AGE_DAYS`,
`NEW_TO_YOU_MAX_AGE_DAYS`._

## 6. Dedup + seen-history

- **Dedup** within a run by apply URL (falls back to company+title).
- **Seen-history** (`seen.json`): any job emailed on a previous run is dropped,
  so you never see the same role twice. Entries expire after 30 days.

## 7. Presentation (not a filter)

- Sorted **freshest first** and grouped into **Today / Yesterday / Earlier**.
- Each job is tagged with the recommended **resume variant** (SWE / Cloud / ML /
  Data) by keyword overlap — this only recommends which of your own resume
  files to use; it never rewrites your resume.

---

## Follow-up rules (post-application)

- A follow-up becomes **due 5 business days** after `date_applied`
  (`FOLLOWUP_BUSINESS_DAYS`).
- The digest drafts a **follow-up email** and a **LinkedIn note** per due item.
- **Email auto-send** (`FOLLOWUP_AUTO_SEND_EMAIL`, default **off**): when on,
  sends **only** to a contact email explicitly on file (from the posting or a
  sheet you import) — never a guessed/scraped personal address. When off, the
  email is drafted for you to send yourself.
- **LinkedIn is always manual**: the digest names who to message (or a search
  hint) and drafts the note; you send it yourself.

---

## Sources currently pulled

Greenhouse, Lever, Ashby (manual lists), Y Combinator (auto-discovered boards),
SimplifyJobs new-grad, four extra GitHub repos (vanshb03, speedyapply, jobright,
Simplify interns), The Muse, Remotive, Himalayas, RemoteOK, plus Adzuna and
USAJobs when their keys are set.
