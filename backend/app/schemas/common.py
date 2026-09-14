from enum import Enum
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ScanMode(str, Enum):
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    RADIO = "radio"


class SessionStatus(str, Enum):
    DRAFT = "draft"
    STARTING = "starting"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CollectorStatus(str, Enum):
    READY = "ready"
    BUSY = "busy"
    PERMISSION_DENIED = "permission_denied"
    ADAPTER_OFF = "adapter_off"
    OFFLINE = "offline"


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)
    
    items: List[T]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
