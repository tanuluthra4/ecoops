from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


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
    # Everything else the engine computed (series, streaks, window, rules...).
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
