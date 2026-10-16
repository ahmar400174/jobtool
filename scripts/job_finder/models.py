"""Shared job record model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    remote: str
    posted: str
    url: str
    source: str
    description: str = ""
    salary: str = ""
    tags: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    def to_row(self) -> dict[str, str]:
        return asdict(self)

    @property
    def dedupe_key(self) -> str:
        title = self.title.lower().strip()
        company = self.company.lower().strip()
        if company in {"", "unknown"}:
            return f"{title}|{self.url}"
        return f"{title}|{company}"
