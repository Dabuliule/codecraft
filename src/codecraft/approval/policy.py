from __future__ import annotations

from enum import StrEnum


class ApprovalPolicy(StrEnum):
    NEVER = "never"
    ON_REQUEST = "on_request"
    UNTRUSTED = "untrusted"
