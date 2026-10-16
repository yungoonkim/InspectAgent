"""Offline-only timeout candidates; never selected by the production API."""

from dataclasses import dataclass
import math
import time

from backend.agent.errors import AgentFailure
from backend.agent.service import AgentService


@dataclass(frozen=True)
class TimeoutPolicy:
    mode: str
    investigation_seconds: int = 15
    final_seconds: int = 30
    overall_seconds: int = 60
    reserve_seconds: int = 2

    def __post_init__(self):
        if self.mode not in {"A", "B", "C"}:
            raise ValueError("INVALID_TIMEOUT_POLICY")
        values = (self.investigation_seconds, self.final_seconds, self.overall_seconds, self.reserve_seconds)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("INVALID_TIMEOUT_POLICY")
        if self.reserve_seconds >= self.overall_seconds:
            raise ValueError("INVALID_TIMEOUT_POLICY")

    def select(self, structured, elapsed_seconds):
        if type(elapsed_seconds) not in (int, float) or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError("INVALID_ELAPSED_TIME")
        requested = self.final_seconds if structured and self.mode != "A" else self.investigation_seconds
        available = math.floor(self.overall_seconds - elapsed_seconds - self.reserve_seconds)
        if available < 1:
            raise AgentFailure("AGENT_TIMEOUT")
        if structured and self.mode == "C":
            return min(requested, available)
        if requested > available:
            raise AgentFailure("AGENT_TIMEOUT")
        return requested


class ExperimentalTimeoutAgent(AgentService):
    """Request-local test subclass; shared production code remains untouched."""

    def __init__(self, *args, policy, clock=time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        if self.limits.request_timeout_seconds != policy.overall_seconds:
            raise ValueError("OVERALL_TIMEOUT_MISMATCH")
        self.policy = policy
        self.clock = clock
        self.started_at = None
        self.timeout_decisions = []

    async def analyze(self, inspection_id):
        self.started_at = self.clock()
        return await super().analyze(inspection_id)

    async def _generate(self, client, model, contents, state, round_number, structured=False):
        elapsed = self.clock() - self.started_at
        seconds = self.policy.select(structured, elapsed)
        self.timeout_decisions.append({"round_number": round_number, "structured": structured, "seconds": seconds})
        original = self.limits
        self.limits = original.model_copy(update={
            "final_model_timeout_seconds" if structured else "model_timeout_seconds": seconds,
        })
        try:
            return await super()._generate(client, model, contents, state, round_number, structured)
        finally:
            self.limits = original
