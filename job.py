"""Shared Job data model and helpers."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    posted_at: Optional[datetime] = None  # timezone-aware UTC when known
    description: str = ""
    extra: dict = field(default_factory=dict)

    def normalized(self) -> "Job":
        """Return a cleaned copy (trimmed strings, UTC posted_at)."""
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        self.location = (self.location or "").strip()
        self.url = (self.url or "").strip()
        if self.posted_at and self.posted_at.tzinfo is None:
            self.posted_at = self.posted_at.replace(tzinfo=timezone.utc)
        return self

    @property
    def dedup_key(self) -> str:
        """Stable key for dedup + seen-history.

        Prefer the URL; fall back to company+title when a URL is missing.
        """
        basis = self.url.lower().strip()
        if not basis:
            basis = f"{self.company.lower()}::{self.title.lower()}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]

    def haystack(self) -> str:
        """Lowercased text used for keyword matching."""
        return f"{self.title} {self.location} {self.description}".lower()
