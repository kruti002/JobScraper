"""
Configuration for the job scraper.

Tuned to Kruti Shah's profile: new-grad / entry-level roles in software
engineering, cloud, data engineering, ML/AI, and backend. Light hardware
(embedded/firmware adjacent to software) is OK; pure hardware roles are excluded.

Edit the lists below to tune what you get emailed.
"""

# --- Time window -------------------------------------------------------------
# Only surface jobs posted within this many hours. Applies to sources that
# expose a RELIABLE post date (The Muse, Adzuna, Arbeitnow, USAJobs, feeds).
# 72h = "last 2-3 days". ATS/YC boards don't have reliable dates, so they use
# the new_to_you (seen-history) strategy instead -- see RECENCY_MODE.
LOOKBACK_HOURS = 72

# Max age (in days) to accept from the SimplifyJobs repo, whose entries carry
# day-granularity age markers like "1d"/"2d" rather than exact timestamps.
SIMPLIFY_MAX_AGE_DAYS = 3

# Recency strategy.
#   "strict"      -> only keep jobs whose timestamp/age is within LOOKBACK_HOURS.
#                    Accurate, but ATS "updated" dates are unreliable so digests
#                    are often nearly empty.
#   "new_to_you"  -> for ATS boards (Greenhouse/Lever/Ashby/YC), skip the clock
#                    and rely on seen.json: email anything not shown before.
#                    SimplifyJobs still uses its reliable age markers.
#                    First run is a big backlog; later runs show only new roles.
RECENCY_MODE = "new_to_you"

# In new_to_you mode, still drop ATS jobs clearly older than this many days
# when a real timestamp IS available (keeps the backlog from being ancient).
NEW_TO_YOU_MAX_AGE_DAYS = 21

# --- Role / seniority matching ----------------------------------------------
# A job title must contain at least one of these to be considered
# entry-level / early-career (new grad OR ~0-1 years of experience).
NEW_GRAD_TITLE_TERMS = [
    "new grad", "new-grad", "newgrad",
    "entry level", "entry-level",
    "early career", "early-career", "early in career",
    "university grad", "university graduate", "college grad",
    "recent grad", "recent graduate",
    "graduate engineer", "graduate software", "grad software",
    "associate engineer", "associate software", "associate developer",
    "junior", "jr ", "jr.",
    "software engineer i", "software engineer 1",
    "engineer i,", "engineer i ", "engineer 1",
    "developer i", "developer 1", "developer i,",
    "swe i", "swe 1", "sde 1", "sde i", "sde-1",
    "campus", "grad 20", "class of 20", "2025 grad", "2026 grad",
    "apprentice", "rotational", "trainee", "emerging talent",
]

# Description phrases that indicate ~0-1 years of experience. If a job title
# doesn't obviously say "new grad" but the description says something like
# "0-1 years" or "0-2 years", we still treat it as early-career.
EARLY_CAREER_DESC_TERMS = [
    "0-1 year", "0 to 1 year", "0-2 year", "0 to 2 year",
    "1+ year", "1-2 year", "1 to 2 year", "up to 2 years",
    "no experience required", "no prior experience",
    "0-1 years of experience", "0-2 years of experience",
    "minimum 0 years", "recent graduate", "recently graduated",
    "entry-level", "early career", "new graduate",
]

# Titles containing any of these are treated as senior and dropped, even if
# they otherwise match a new-grad term.
SENIOR_TITLE_TERMS = [
    "senior", "sr.", "sr ", "staff", "principal", "lead ", "manager",
    "director", "head of", "vp ", "vice president", "architect",
    "ii", "iii", "iv", "level 2", "level 3", "l4", "l5", "l6",
    "engineer ii", "engineer iii", "10+ years", "8+ years", "7+ years",
    "5+ years", "6+ years",
]

# --- Domain keywords (title OR description should hit at least one) ----------
TARGET_KEYWORDS = [
    "software", "swe", "developer", "backend", "back-end", "back end",
    "full stack", "fullstack", "full-stack", "frontend", "front-end",
    "cloud", "aws", "gcp", "azure", "devops", "sre", "site reliability",
    "platform", "infrastructure", "distributed",
    "data engineer", "data engineering", "etl", "pipeline", "analytics",
    "machine learning", "ml engineer", "ai engineer", "mlops",
    "nlp", "deep learning", "computer vision", "llm", "gen ai", "genai",
    "python", "java", "c++", "golang", "typescript", "react", "node",
    "api", "microservice", "systems engineer",
    "embedded software", "firmware",  # light hardware OK
]

# Titles/descriptions containing these are pure-hardware and get excluded.
HARDWARE_EXCLUDE_TERMS = [
    "asic", "vlsi", "rtl design", "pcb", "analog design", "rf engineer",
    "semiconductor", "chip design", "circuit design", "hardware design",
    "mechanical engineer", "electrical engineer", "fpga design",
    "signal integrity", "power electronics", "cadence", "verilog design",
]

# Non-tech / unrelated roles to always drop.
GLOBAL_EXCLUDE_TERMS = [
    "sales", "marketing", "recruiter", "recruiting", "account executive",
    "customer success", "nurse", "physician", "attorney", "accountant",
    "warehouse", "driver", "barista", "cashier", "janitor",
]

# --- Timing / target season --------------------------------------------------
# You're targeting Summer 2027 (graduating May 2027). Jobs whose title/desc
# clearly point to an EARLIER season/year are dropped. Jobs with NO season/year
# mentioned are KEPT (per your rule: "if nothing written then it's fine").
#
# TARGET_SEASON_TERMS: phrases that mark a role as the season you want. If any
# of these appear, the job is kept regardless of other year mentions.
TARGET_SEASON_TERMS = [
    "2027", "summer 2027", "2026-2027", "2026 - 2027", "class of 2027",
    "winter 2027", "spring 2027", "fall 2027",
]
# PAST_SEASON_TERMS: phrases that mark a role as too early for you. If one of
# these appears AND no TARGET_SEASON_TERMS appears, the job is dropped.
PAST_SEASON_TERMS = [
    "2024", "summer 2024", "fall 2024", "winter 2024", "spring 2024",
    "2025", "summer 2025", "fall 2025", "winter 2025", "spring 2025",
    "class of 2025", "2026", "summer 2026", "fall 2026", "spring 2026",
    "winter 2026", "class of 2026", "immediate start", "start immediately",
    "immediately available", "asap start",
]

# Jobs that REQUIRE US citizenship (or a security clearance that implies it)
# are excluded, since they're not open to non-citizens. If a description says
# citizenship but frames it as "authorized to work" only, that's fine and NOT
# matched here.
CITIZENSHIP_EXCLUDE_TERMS = [
    "u.s. citizenship required", "us citizenship required",
    "must be a u.s. citizen", "must be a us citizen",
    "must be us citizen", "must be a citizen",
    "requires u.s. citizenship", "requires us citizenship",
    "u.s. citizenship is required", "us citizenship is required",
    "citizenship required", "citizens only", "u.s. citizens only",
    "us citizens only", "active security clearance",
    "active secret clearance", "active top secret", "ts/sci",
    "security clearance required", "must possess a security clearance",
    "ability to obtain a security clearance",
]

# --- Location preferences ----------------------------------------------------
# Jobs matching these locations are kept. Remote is always kept. Set to []
# to disable location filtering entirely (keep everything).
PREFERRED_LOCATION_TERMS = [
    "remote", "united states", "usa", "us -", ", us", "colorado", "denver",
    "boulder", "co ", "california", "washington", "new york", "texas",
    "seattle", "san francisco", "bay area", "austin", "boston", "chicago",
    "atlanta", "hybrid", "anywhere",
]
# If True, jobs with no parseable location are kept (better recall).
KEEP_UNKNOWN_LOCATION = True

# --- Sources -----------------------------------------------------------------
# Greenhouse: board tokens (the slug in boards.greenhouse.io/<token>).
# All verified to return 200 from the public boards API. A wrong slug just
# logs a 404 and is skipped, so it's safe to add more.
GREENHOUSE_BOARDS = [
    # big / public tech
    "stripe", "databricks", "airbnb", "coinbase", "robinhood", "brex",
    "gusto", "asana", "dropbox", "instacart", "reddit", "figma", "affirm",
    "twilio", "cloudflare", "datadog", "gitlab", "elastic", "samsara",
    "scaleai", "anthropic", "pinterest", "lyft", "roblox", "flexport",
    "peloton", "discord", "nextdoor", "medium", "duolingo", "coursera",
    "udemy", "mongodb", "toast", "squarespace", "zscaler", "okta",
    # fintech
    "gemini", "chime", "sofi", "carta", "mercury", "alloy",
    "nubank", "current", "betterment", "public", "wise", "monzo",
    # crypto / web3
    "fireblocks", "ripple", "consensys",
    # infra / dev tools / data / startups
    "cockroachlabs", "checkr", "webflow", "fivetran", "tailscale",
    "planetscale", "netlify", "vercel", "airtable", "faire", "verkada",
    "mixpanel", "sendbird", "vonage", "hightouch",
    "starburst", "imply", "singlestore", "yugabyte",
    # AI
    "stabilityai",
]

# Lever: company slugs (jobs.lever.co/<slug>).
LEVER_COMPANIES = [
    "palantir", "mistral", "voleon", "matchgroup",
    "spotify", "kraken",
]

# Ashby: org slugs (jobs.ashbyhq.com/<slug>).
# Heavy on AI-native startups (which mostly use Ashby) plus fintech/dev tools.
ASHBY_COMPANIES = [
    "openai", "ramp", "linear", "notion", "mercury", "vercel", "runway",
    "clickhouse", "supabase", "replit", "cursor", "modal", "baseten",
    "harvey", "cohere", "character", "watershed", "sierra", "writer",
    "decagon", "abridge", "openevidence", "sardine", "deel",
    "elevenlabs", "suno", "pika", "midjourney",
    # AI labs / infra
    "perplexity", "lambda", "crusoe", "cerebras", "cognition", "poolside",
    "mercor", "turing", "figure", "1x",
    # dev tools
    "clerk", "resend", "warp", "raycast", "browserbase", "e2b",
    "mintlify", "inngest",
    # AI apps / consumer
    "wispr-flow", "granola", "cluely", "lovable", "bolt",
]

# USAJobs API keyword search terms (public API; needs free API key).
USAJOBS_KEYWORDS = [
    "software engineer", "data engineer", "computer scientist",
]

# Y Combinator: auto-discover public job boards for YC companies that are
# hiring, via the public yc-oss API. Boards are cached in yc_boards.json
# (refresh with: python yc.py --discover). This adds hundreds of startup
# boards without manual slug hunting.
ENABLE_YC = True
YC_DISCOVER_LIMIT = 1483  # max YC companies probed during discovery (all hiring)

# SimplifyJobs New-Grad repo (raw README parsed for recent entries).
SIMPLIFY_NEWGRAD_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "New-Grad-Positions/dev/README.md"
)

# Additional curated new-grad / early-career GitHub repos. All use the same
# HTML-table README format as SimplifyJobs, so they share one parser. Each is
# (source_label, raw_readme_url). A 404 or format change just logs and skips.
ENABLE_GITHUB_REPOS = True
GITHUB_REPO_LISTS = [
    ("github-vanshb03",
     "https://raw.githubusercontent.com/vanshb03/New-Grad-2025/main/README.md"),
    ("github-speedyapply",
     "https://raw.githubusercontent.com/speedyapply/2025-SWE-College-Jobs/main/README.md"),
    ("github-jobright",
     "https://raw.githubusercontent.com/jobright-ai/2025-Software-Engineer-New-Grad/master/README.md"),
    ("github-simplify-intern",
     "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"),
]

# Remotive (public, no key).
ENABLE_REMOTIVE = True
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTIVE_CATEGORIES = ["software-dev", "data"]

# Himalayas (public remote-jobs API, no key).
ENABLE_HIMALAYAS = True
HIMALAYAS_URL = "https://himalayas.app/jobs/api"
HIMALAYAS_MAX_PAGES = 3  # 20/page

# RemoteOK API (public JSON feed).
REMOTEOK_URL = "https://remoteok.com/api"

# --- Aggregator APIs (reliable post dates; use LOOKBACK_HOURS) ---------------
# The Muse (public, no key). Categories + experience levels filterable.
ENABLE_THEMUSE = True
THEMUSE_CATEGORIES = [
    "Software Engineering", "Data Science", "Data and Analytics",
    "Engineering", "Computer and IT", "Science and Engineering",
]
THEMUSE_LEVELS = ["Entry Level", "Internship"]  # the Muse's own level buckets
THEMUSE_MAX_PAGES = 5  # pages per category (20 jobs/page)

# Arbeitnow (public, no key). EU-heavy but has remote/US roles; location
# filtering handles the rest.
ENABLE_ARBEITNOW = True
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_MAX_PAGES = 3

# Adzuna (free developer key: https://developer.adzuna.com/). Aggregates
# thousands of sources. Set ADZUNA_APP_ID + ADZUNA_APP_KEY as env/secrets.
# Skipped automatically if the key isn't set.
ENABLE_ADZUNA = True
ADZUNA_COUNTRY = "us"
ADZUNA_QUERIES = [
    "software engineer", "data engineer", "machine learning engineer",
    "backend engineer", "cloud engineer",
]
ADZUNA_MAX_DAYS_OLD = 3
ADZUNA_RESULTS_PER_PAGE = 50

# --- Email -------------------------------------------------------------------
EMAIL_TO = "krutis1972@gmail.com"
EMAIL_SUBJECT_PREFIX = "New Grad Tech Jobs"

# --- Applications tracking + follow-ups --------------------------------------
# Business days after you apply before a follow-up is surfaced in the digest.
FOLLOWUP_BUSINESS_DAYS = 5

# Auto-send the follow-up EMAIL when a real contact_email is on file. When
# False (default), follow-ups are DRAFTED in the digest for you to send
# yourself. Even when True, this only ever sends to an explicitly provided
# contact_email -- never a guessed/scraped personal address. LinkedIn is
# always manual (we only tell you who to message + draft the note).
FOLLOWUP_AUTO_SEND_EMAIL = False

# Identity used in follow-up drafts.
APPLICANT_NAME = "Kruti Shah"
APPLICANT_CONTACT_LINE = "krutis1972@gmail.com | linkedin.com/in/kruti-shah-cs95"

# --- Resume variants ---------------------------------------------------------
# The matcher picks the best-fit lane per job by keyword overlap. It only
# RECOMMENDS which of your own resume files to use -- it never rewrites them.
RESUME_VARIANTS = {
    "SWE": [
        "software engineer", "backend", "back-end", "full stack", "fullstack",
        "frontend", "api", "microservice", "java", "typescript", "node",
        "react", "systems", "distributed", "developer", "swe", "sde",
    ],
    "Cloud": [
        "cloud", "aws", "gcp", "azure", "devops", "sre", "site reliability",
        "platform", "infrastructure", "kubernetes", "docker", "terraform",
        "ci/cd", "reliability",
    ],
    "ML": [
        "machine learning", "ml engineer", "ai engineer", "mlops", "nlp",
        "deep learning", "computer vision", "llm", "gen ai", "genai",
        "pytorch", "tensorflow", "transformers", "rag", "model",
    ],
    "Data": [
        "data engineer", "data engineering", "etl", "pipeline", "analytics",
        "spark", "airflow", "warehouse", "sql", "snowflake", "databricks",
        "dbt", "data platform",
    ],
}
# Tie-break order (earlier = preferred when scores tie).
RESUME_VARIANT_ORDER = ["SWE", "ML", "Cloud", "Data"]
RESUME_DEFAULT_VARIANT = "SWE"
# Optional: map a variant to the resume file you'd attach for it.
RESUME_FILES = {
    "SWE": "config/resume_swe.pdf",
    "Cloud": "config/resume_cloud.pdf",
    "ML": "config/resume_ml.pdf",
    "Data": "config/resume_data.pdf",
}

# HTTP niceties
REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = "job-digest-bot/1.0 (personal use)"
