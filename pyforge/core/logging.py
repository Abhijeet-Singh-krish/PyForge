"""Structured JSON Logging with Sensitive Field Redaction (Section 35)."""
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict

SENSITIVE_KEYS = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "secret_key", "api_key", "cookie", "authorization", "session_token"
}

def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = redact_dict(v)
        else:
            cleaned[k] = v
    return cleaned

def log_event(level: str, event: str, request_id: str | None = None, execution_id: str | None = None, **fields: Any) -> str:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
        "request_id": request_id,
        "execution_id": execution_id,
        **redact_dict(fields),
    }
    serialized = json.dumps(record, default=str)
    return serialized
