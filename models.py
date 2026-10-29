"""Small data models shared by the dashboard components."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DeviceStatus:
    unit: str
    connected: bool = False
    ready: bool = False
    last_message_at: Optional[datetime] = None


@dataclass
class Trial:
    session_id: int
    received_at: datetime
    source_unit: str
    route: str
    uid_display: str = ""
    rtt_ms: Optional[float] = None
    threshold_ms: Optional[float] = None
    proof_valid: Optional[bool] = None
    secret_used: Optional[bool] = None
    decision: str = "error"
    reason: str = ""
