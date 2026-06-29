"""Enumerations shared across ORM models and API schemas."""

from __future__ import annotations

from enum import StrEnum


class ChatStatus(StrEnum):
    created = "created"
    running = "running"
    completed = "completed"
    failed = "failed"


class AgentRunPhase(StrEnum):
    deliberation = "deliberation"  # Phase A: a council member
    synthesis = "synthesis"  # Phase B: the Chairman


class AgentRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class MessageAuthorType(StrEnum):
    user = "user"
    agent = "agent"
    system = "system"
