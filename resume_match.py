"""
Resume-variant matcher.

Given a job, score it against each of your resume lanes by keyword overlap and
return the best-fit variant label (e.g. "SWE", "Cloud", "ML", "Data"). This
does NOT rewrite your resume -- it just recommends which variant you control
to use for a given role.

Keep your actual resume files wherever you like (e.g. config/resume_swe.pdf);
this module only decides the label. Wire the file paths in config.RESUME_FILES
if you want the digest to name the exact file to attach.
"""
from __future__ import annotations

from typing import Dict

import config
from job import Job


def best_variant(job: Job) -> str:
    """Return the best-fit resume variant label for a job."""
    hay = job.haystack()
    scores: Dict[str, int] = {}
    for label, keywords in config.RESUME_VARIANTS.items():
        scores[label] = sum(1 for kw in keywords if kw in hay)
    # Highest score wins; ties fall back to the configured default order.
    best = max(config.RESUME_VARIANTS.keys(),
               key=lambda l: (scores[l], -config.RESUME_VARIANT_ORDER.index(l)))
    if scores[best] == 0:
        return config.RESUME_DEFAULT_VARIANT
    return best


def variant_file(label: str) -> str:
    """Optional: the resume file to attach for a variant, if configured."""
    return config.RESUME_FILES.get(label, "")
