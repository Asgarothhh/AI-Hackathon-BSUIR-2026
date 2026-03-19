from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class KnowledgePage:
    slug: str
    title: str
    chapter: str
    markdown: str
    sources: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.utcnow)
