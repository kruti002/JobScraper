"""
Source fetchers. Each function returns a list[Job]. Failures in one source
never crash the run: they log and return [].

Sources:
  - Greenhouse  (boards-api.greenhouse.io)          public JSON
  - Lever       (api.lever.co/v0/postings)           public JSON
  - Ashby       (api.ashbyhq.com/posting-api)         public JSON
  - USAJobs     (data.usajobs.gov/api/search)         needs free API key
  - RemoteOK    (remoteok.com/api)                    public JSON
  - SimplifyJobs New-Grad repo README                 parsed markdown
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from typing import List

import requests
from dateutil import parser as dateparser

import config
from job import Job


def _log(msg: str) -> None:
    print(f"[sources] {msg}", file=sys.stderr)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    return s


def _parse_dt(value) -> "datetime | None":
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # epoch seconds or millis
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        dt = dateparser.parse(str(value))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OverflowError, TypeError):
        return None


# --- Greenhouse --------------------------------------------------------------
def fetch_greenhouse(boards: List[str]) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    for token in boards:
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            "?content=true"
        )
        try:
            r = s.get(url, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"greenhouse {token}: HTTP {r.status_code}")
                continue
            data = r.json()
            for item in data.get("jobs", []):
                loc = (item.get("location") or {}).get("name", "")
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=token,
                        location=loc,
                        url=item.get("absolute_url", ""),
                        source="greenhouse",
                        posted_at=_parse_dt(item.get("updated_at")),
                        description=re.sub(r"<[^>]+>", " ", item.get("content", "") or ""),
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"greenhouse {token}: {e}")
    _log(f"greenhouse: {len(jobs)} raw jobs from {len(boards)} boards")
    return jobs


# --- Lever -------------------------------------------------------------------
def fetch_lever(companies: List[str]) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    for slug in companies:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            r = s.get(url, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"lever {slug}: HTTP {r.status_code}")
                continue
            for item in r.json():
                cats = item.get("categories", {}) or {}
                loc = cats.get("location", "") or ""
                desc = item.get("descriptionPlain") or item.get("description", "") or ""
                jobs.append(
                    Job(
                        title=item.get("text", ""),
                        company=slug,
                        location=loc,
                        url=item.get("hostedUrl", "") or item.get("applyUrl", ""),
                        source="lever",
                        posted_at=_parse_dt(item.get("createdAt")),
                        description=re.sub(r"<[^>]+>", " ", desc),
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"lever {slug}: {e}")
    _log(f"lever: {len(jobs)} raw jobs from {len(companies)} companies")
    return jobs


# --- Ashby -------------------------------------------------------------------
def fetch_ashby(companies: List[str]) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    for slug in companies:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        try:
            r = s.get(url, params={"includeCompensation": "false"},
                      timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"ashby {slug}: HTTP {r.status_code}")
                continue
            data = r.json()
            for item in data.get("jobs", []):
                loc = item.get("location", "") or ""
                if item.get("isRemote"):
                    loc = (loc + " Remote").strip()
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=slug,
                        location=loc,
                        url=item.get("jobUrl", "") or item.get("applyUrl", ""),
                        source="ashby",
                        posted_at=_parse_dt(item.get("publishedAt") or item.get("updatedAt")),
                        description=item.get("descriptionPlain", "") or "",
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"ashby {slug}: {e}")
    _log(f"ashby: {len(jobs)} raw jobs from {len(companies)} companies")
    return jobs


# --- USAJobs -----------------------------------------------------------------
def fetch_usajobs(keywords: List[str]) -> List[Job]:
    api_key = os.environ.get("USAJOBS_API_KEY", "").strip()
    email = os.environ.get("USAJOBS_EMAIL", "").strip()
    if not api_key or not email:
        _log("usajobs: skipped (USAJOBS_API_KEY / USAJOBS_EMAIL not set)")
        return []

    jobs: List[Job] = []
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": email,
        "Authorization-Key": api_key,
    }
    for kw in keywords:
        url = "https://data.usajobs.gov/api/search"
        params = {
            "Keyword": kw,
            "DatePosted": 1,          # posted within last 1 day
            "ResultsPerPage": 50,
            "SortField": "opendate",
            "SortDirection": "Desc",
        }
        try:
            r = requests.get(url, headers=headers, params=params,
                             timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"usajobs '{kw}': HTTP {r.status_code}")
                continue
            items = (
                r.json()
                .get("SearchResult", {})
                .get("SearchResultItems", [])
            )
            for wrap in items:
                d = wrap.get("MatchedObjectDescriptor", {})
                locs = d.get("PositionLocationDisplay", "")
                jobs.append(
                    Job(
                        title=d.get("PositionTitle", ""),
                        company=d.get("OrganizationName", "US Government"),
                        location=locs,
                        url=d.get("PositionURI", ""),
                        source="usajobs",
                        posted_at=_parse_dt(d.get("PublicationStartDate")),
                        description=(d.get("UserArea", {})
                                     .get("Details", {})
                                     .get("JobSummary", "")) or
                                    d.get("QualificationSummary", "") or "",
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"usajobs '{kw}': {e}")
    _log(f"usajobs: {len(jobs)} raw jobs")
    return jobs


# --- RemoteOK ----------------------------------------------------------------
def fetch_remoteok() -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    # RemoteOK is picky about UA; give it a browser-ish one.
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; job-digest-bot/1.0)"})
    try:
        r = s.get(config.REMOTEOK_URL, timeout=config.REQUEST_TIMEOUT)
        if r.status_code != 200:
            _log(f"remoteok: HTTP {r.status_code}")
            return []
        data = r.json()
        for item in data:
            # first element is a legal/metadata notice
            if not isinstance(item, dict) or "position" not in item:
                continue
            title = item.get("position", "") or item.get("title", "")
            loc = item.get("location", "") or "Remote"
            jobs.append(
                Job(
                    title=title,
                    company=item.get("company", ""),
                    location=(loc + " Remote") if "remote" not in loc.lower() else loc,
                    url=item.get("url", ""),
                    source="remoteok",
                    posted_at=_parse_dt(item.get("date") or item.get("epoch")),
                    description=re.sub(r"<[^>]+>", " ", item.get("description", "") or ""),
                ).normalized()
            )
    except (requests.RequestException, ValueError) as e:
        _log(f"remoteok: {e}")
    _log(f"remoteok: {len(jobs)} raw jobs")
    return jobs


# --- SimplifyJobs New-Grad repo ---------------------------------------------
# The README lists jobs in HTML <table> rows (not markdown pipes). Each job is
# a <tr> with 5 <td> cells: Company, Role, Location, Application, Age.
#   Company:  <strong><a href="...">Name</a></strong>  (may carry emoji flags)
#   Role:     plain text
#   Location: text, may contain <br>/<details> for multiple locations
#   App:      first <a href> is the direct apply link; simplify.jobs is second
#   Age:      e.g. "2d", "3d", "8h"
# A company cell of "↳" means "same company as the row above".
_TR = re.compile(r"<tr>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
_HREF = re.compile(r'href="([^"]+)"')
_TAG = re.compile(r"<[^>]+>")
# emoji / flag markers used in the list that we strip from company/role text
_FLAGS = ("🛂", "🇺🇸", "🔒", "🔥", "🎓", "↳", "�√")


def _clean_text(text: str) -> str:
    text = text.replace("</br>", " ").replace("<br>", " ").replace("<br/>", " ")
    text = _TAG.sub(" ", text)
    for f in _FLAGS:
        text = text.replace(f, " ")
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _is_closed(cell_html: str) -> bool:
    return "🔒" in cell_html


def _requires_citizenship(row_html: str) -> bool:
    # Legend: 🇺🇸 = Requires U.S. Citizenship (usually on company or role cell)
    return "🇺🇸" in row_html


def _pick_apply_url(app_cell: str) -> str:
    """Return the direct apply link (first non-simplify.jobs href)."""
    hrefs = _HREF.findall(app_cell)
    for h in hrefs:
        if "simplify.jobs" not in h:
            return h
    return hrefs[0] if hrefs else ""


def _parse_repo_readme(text: str, source_label: str) -> List[Job]:
    """Parse a SimplifyJobs-style HTML-table README into Jobs."""
    jobs: List[Job] = []
    last_company = ""
    for row in _TR.findall(text):
        cells = _TD.findall(row)
        if len(cells) < 4:
            continue  # header rows use <th>, skipped naturally

        company_raw = _clean_text(cells[0])
        is_ditto = "↳" in cells[0] or not company_raw
        company = last_company if is_ditto else company_raw
        if not is_ditto:
            last_company = company

        if _is_closed(cells[3]):
            continue  # application closed

        role = _clean_text(cells[1])
        location = _clean_text(cells[2])
        url = _pick_apply_url(cells[3])
        age = _clean_text(cells[4]) if len(cells) > 4 else ""
        citizenship = _requires_citizenship(row)

        if not role or not url or url.startswith("#"):
            continue

        jobs.append(
            Job(
                title=role,
                company=company or "Unknown",
                location=location,
                url=url,
                source=source_label,
                posted_at=None,  # recency derived from the age marker
                description="",
                extra={"age": age, "citizenship": citizenship},
            ).normalized()
        )
    return jobs


def fetch_simplify_newgrad() -> List[Job]:
    s = _session()
    s.headers.update({"Accept": "text/plain"})
    jobs: List[Job] = []
    try:
        r = s.get(config.SIMPLIFY_NEWGRAD_URL, timeout=config.REQUEST_TIMEOUT)
        if r.status_code != 200:
            _log(f"simplify: HTTP {r.status_code}")
            return []
        jobs = _parse_repo_readme(r.text, "simplify-newgrad")
    except (requests.RequestException, ValueError) as e:
        _log(f"simplify: {e}")
    _log(f"simplify: {len(jobs)} raw jobs")
    return jobs


_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _parse_markdown_table(text: str, source_label: str) -> List[Job]:
    """Parse a Markdown pipe-table README (| Company | Role | Loc | Link | Age |).

    Column names vary across repos (Role/Position/Job Title, Date Posted/Age),
    so we locate columns from the header row.
    """
    jobs: List[Job] = []
    lines = text.splitlines()
    header_idx = None
    cols: List[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|") and "company" in s.lower() and "|" in s[1:]:
            cols = [c.strip().lower() for c in s.strip("|").split("|")]
            header_idx = i
            break
    if header_idx is None:
        return jobs

    def col(*names):
        for n in names:
            for idx, c in enumerate(cols):
                if n in c:
                    return idx
        return None

    ci = {
        "company": col("company"),
        "role": col("role", "position", "job title", "title"),
        "loc": col("location"),
        "link": col("application", "link", "posting", "apply"),
        "age": col("date posted", "age", "date", "posted"),
    }

    last_company = ""
    for line in lines[header_idx + 2:]:  # skip header + separator
        s = line.strip()
        if not s.startswith("|"):
            if jobs:  # table ended
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue

        def cell(key):
            idx = ci[key]
            return cells[idx] if idx is not None and idx < len(cells) else ""

        company_raw = _clean_text(_MD_LINK.sub(r"\1", cell("company")))
        is_ditto = "↳" in cell("company") or not company_raw
        company = last_company if is_ditto else company_raw
        if not is_ditto:
            last_company = company

        role_cell = cell("role")
        role = _clean_text(_MD_LINK.sub(r"\1", role_cell))

        # URL: prefer a link in the application/link column, else in the role.
        url = ""
        for src_cell in (cell("link"), role_cell, cell("company")):
            m = _HREF.search(src_cell) or _MD_LINK.search(src_cell)
            if m:
                url = m.group(1) if m.re is _HREF else m.group(2)
                if url and not url.startswith("#"):
                    break
                url = ""
        if _is_closed(cell("link")):
            continue

        location = _clean_text(_MD_LINK.sub(r"\1", cell("loc")))
        age = _clean_text(cell("age"))
        citizenship = "🇺🇸" in line

        if not role or not url:
            continue

        # Age may be relative ("1d","8h") or an absolute date ("Oct 06",
        # "Aug 05"). Parse absolute dates into a real posted_at so recency
        # works; leave relative markers in extra['age'].
        posted = None
        rel = age.lower()
        if not (rel.endswith(("d", "h", "m")) and rel[:-1].strip().isdigit()):
            posted = _parse_dt(age)  # tries to parse "Oct 06" etc.
            if posted is None and age:
                # unparseable, non-relative -> keep via age marker fallback
                pass

        jobs.append(
            Job(
                title=role,
                company=company or "Unknown",
                location=location,
                url=url,
                source=source_label,
                posted_at=posted,
                description="",
                extra={"age": age, "citizenship": citizenship},
            ).normalized()
        )
    return jobs


def fetch_github_repos(repos) -> List[Job]:
    """Parse curated new-grad repos. Supports both HTML-table and Markdown-table
    README formats (auto-detected)."""
    s = _session()
    s.headers.update({"Accept": "text/plain"})
    all_jobs: List[Job] = []
    for label, url in repos:
        try:
            r = s.get(url, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"{label}: HTTP {r.status_code}")
                continue
            if "<tr>" in r.text or "<tr " in r.text:
                got = _parse_repo_readme(r.text, label)
            else:
                got = _parse_markdown_table(r.text, label)
            _log(f"{label}: {len(got)} raw jobs")
            all_jobs += got
        except (requests.RequestException, ValueError) as e:
            _log(f"{label}: {e}")
    return all_jobs


# --- The Muse ----------------------------------------------------------------
def fetch_themuse(categories, levels, max_pages) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (job-digest-bot/1.0)"})
    level_set = {l.lower() for l in levels}
    for cat in categories:
        for page in range(1, max_pages + 1):
            try:
                r = s.get(
                    "https://www.themuse.com/api/public/jobs",
                    params={"category": cat, "page": page, "descending": "true"},
                    timeout=config.REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    break
                results = r.json().get("results", [])
                if not results:
                    break
                for item in results:
                    lv = {l.get("name", "").lower() for l in item.get("levels", [])}
                    if level_set and not (lv & level_set):
                        continue
                    locs = ", ".join(l.get("name", "")
                                     for l in item.get("locations", []))
                    jobs.append(
                        Job(
                            title=item.get("name", ""),
                            company=(item.get("company") or {}).get("name", ""),
                            location=locs,
                            url=(item.get("refs") or {}).get("landing_page", ""),
                            source="themuse",
                            posted_at=_parse_dt(item.get("publication_date")),
                            description=re.sub(r"<[^>]+>", " ",
                                               item.get("contents", "") or ""),
                        ).normalized()
                    )
            except (requests.RequestException, ValueError) as e:
                _log(f"themuse {cat} p{page}: {e}")
                break
    _log(f"themuse: {len(jobs)} raw jobs")
    return jobs


# --- Remotive ----------------------------------------------------------------
def fetch_remotive(categories) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (job-digest-bot/1.0)"})
    for cat in categories:
        try:
            r = s.get(config.REMOTIVE_URL, params={"category": cat},
                      timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                _log(f"remotive {cat}: HTTP {r.status_code}")
                continue
            for item in r.json().get("jobs", []):
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        location=item.get("candidate_required_location", "") or "Remote",
                        url=item.get("url", ""),
                        source="remotive",
                        posted_at=_parse_dt(item.get("publication_date")),
                        description=re.sub(r"<[^>]+>", " ",
                                           item.get("description", "") or ""),
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"remotive {cat}: {e}")
    _log(f"remotive: {len(jobs)} raw jobs")
    return jobs


# --- Himalayas ---------------------------------------------------------------
def fetch_himalayas(max_pages) -> List[Job]:
    jobs: List[Job] = []
    s = _session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (job-digest-bot/1.0)"})
    for page in range(max_pages):
        try:
            r = s.get(config.HIMALAYAS_URL,
                      params={"limit": 20, "offset": page * 20},
                      timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("jobs", []) if isinstance(data, dict) else []
            if not items:
                break
            for item in items:
                locs = ", ".join(item.get("locationRestrictions", []) or []) or "Remote"
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=item.get("companyName", ""),
                        location=locs,
                        url=item.get("applicationLink", "") or item.get("guid", ""),
                        source="himalayas",
                        posted_at=_parse_dt(item.get("pubDate")),
                        description=re.sub(r"<[^>]+>", " ",
                                           item.get("description", "") or
                                           item.get("excerpt", "") or ""),
                        extra={"seniority": item.get("seniority", "")},
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"himalayas p{page}: {e}")
            break
    _log(f"himalayas: {len(jobs)} raw jobs")
    return jobs


# --- Adzuna ------------------------------------------------------------------
def fetch_adzuna(queries) -> List[Job]:
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        _log("adzuna: skipped (ADZUNA_APP_ID / ADZUNA_APP_KEY not set)")
        return []
    jobs: List[Job] = []
    s = _session()
    base = f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search"
    for q in queries:
        try:
            r = s.get(
                f"{base}/1",
                params={
                    "app_id": app_id, "app_key": app_key,
                    "what": q, "results_per_page": config.ADZUNA_RESULTS_PER_PAGE,
                    "max_days_old": config.ADZUNA_MAX_DAYS_OLD,
                    "sort_by": "date", "content-type": "application/json",
                },
                timeout=config.REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                _log(f"adzuna '{q}': HTTP {r.status_code}")
                continue
            for item in r.json().get("results", []):
                loc = (item.get("location") or {}).get("display_name", "")
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=(item.get("company") or {}).get("display_name", ""),
                        location=loc,
                        url=item.get("redirect_url", ""),
                        source="adzuna",
                        posted_at=_parse_dt(item.get("created")),
                        description=re.sub(r"<[^>]+>", " ",
                                           item.get("description", "") or ""),
                    ).normalized()
                )
        except (requests.RequestException, ValueError) as e:
            _log(f"adzuna '{q}': {e}")
    _log(f"adzuna: {len(jobs)} raw jobs")
    return jobs


def fetch_all() -> List[Job]:
    jobs: List[Job] = []
    jobs += fetch_greenhouse(config.GREENHOUSE_BOARDS)
    jobs += fetch_lever(config.LEVER_COMPANIES)
    jobs += fetch_ashby(config.ASHBY_COMPANIES)
    jobs += fetch_usajobs(config.USAJOBS_KEYWORDS)
    jobs += fetch_remoteok()
    jobs += fetch_simplify_newgrad()
    # Extra curated GitHub new-grad/early-career repos
    if config.ENABLE_GITHUB_REPOS:
        jobs += fetch_github_repos(config.GITHUB_REPO_LISTS)
    # Aggregator APIs (reliable post dates)
    if config.ENABLE_THEMUSE:
        jobs += fetch_themuse(config.THEMUSE_CATEGORIES, config.THEMUSE_LEVELS,
                              config.THEMUSE_MAX_PAGES)
    if config.ENABLE_REMOTIVE:
        jobs += fetch_remotive(config.REMOTIVE_CATEGORIES)
    if config.ENABLE_HIMALAYAS:
        jobs += fetch_himalayas(config.HIMALAYAS_MAX_PAGES)
    if config.ENABLE_ADZUNA:
        jobs += fetch_adzuna(config.ADZUNA_QUERIES)
    # Y Combinator companies (auto-discovered boards, cached in yc_boards.json)
    if config.ENABLE_YC:
        try:
            import yc
            jobs += yc.fetch_yc()
        except Exception as e:  # never let YC break the whole run
            _log(f"yc source failed: {e}")
    _log(f"TOTAL raw jobs collected: {len(jobs)}")
    return jobs
