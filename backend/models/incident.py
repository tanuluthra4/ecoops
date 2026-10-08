from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Incident:
    incident_id: str
    type: str
    severity: str
    location: str
    max_temp: Optional[float]
    avg_temp: Optional[float]
    hot_streak_hours: int
    threshold: float
    valid_observations: int
    evidence: List[str] = field(default_factory=list)