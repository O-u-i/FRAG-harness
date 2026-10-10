"""Model-free shared reservations. Synthetic tariffs are NOT provider guarantees."""
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from uuid import uuid4

from frag_api.schemas.workflow import BudgetSnapshot


class BudgetRejected(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def integer(value):
    return type(value) is int and value >= 0


@dataclass(frozen=True)
class SyntheticTariff:
    input_micro_cny: int = 2
    output_micro_cny: int = 10
    request_fee_micro_cny: int = 0

    def __post_init__(self):
        if not all(integer(value) for value in (self.input_micro_cny, self.output_micro_cny, self.request_fee_micro_cny)):
            raise ValueError("Invalid synthetic tariff.")

    def liability(self, inputs, outputs):
        return inputs * self.input_micro_cny + outputs * self.output_micro_cny + self.request_fee_micro_cny


class WorkflowBudget:
    """One lifetime, including evidence work; neither retries nor remediation reset it."""
    duration_seconds = 600
    max_input = 100_000
    max_output = 50_000
    max_micro_cny = 1_000_000

    def __init__(self, *, clock=monotonic, tariff=None):
        self._lock = RLock()
        self._clock = clock
        self._started = clock()
        self._tariff = tariff or SyntheticTariff()
        self._requests = {}
        self._unknown = False
        self._stopped = False
        self._remediation = 0
        self._last_failure = None

    def _live(self):
        if self._stopped:
            raise BudgetRejected("STATE_CONFLICT")
        if self._clock() - self._started >= self.duration_seconds:
            raise BudgetRejected("DEADLINE_EXCEEDED")

    def stop(self):
        with self._lock:
            self._stopped = True

    def snapshot(self):
        with self._lock:
            return BudgetSnapshot(inputTokens=sum(r[0] for r in self._requests.values()),
                outputTokens=sum(r[1] for r in self._requests.values()),
                liabilityMicroCny=sum(r[2] for r in self._requests.values()),
                pendingRequests=sum(r[3] == "pending" for r in self._requests.values()),
                usageUnknown=self._unknown, attempts=1 + self._remediation, remediationRounds=self._remediation)

    def reserve(self, complete_input_tokens, max_counted_output_tokens, *, model="gpt-6.1-sol", effort="high"):
        """Caller must count ALL transmitted input and ALL billable output/reasoning."""
        with self._lock:
            self._live()
            if self._unknown:
                raise BudgetRejected("USAGE_UNKNOWN")
            if model != "gpt-6.1-sol" or effort != "high":
                raise BudgetRejected("MODEL_MISMATCH")
            if not integer(complete_input_tokens) or not integer(max_counted_output_tokens) or max_counted_output_tokens == 0:
                raise BudgetRejected("TOKEN_LIMIT")
            current = self.snapshot()
            charge = self._tariff.liability(complete_input_tokens, max_counted_output_tokens)
            if current.input_tokens + complete_input_tokens > self.max_input or current.output_tokens + max_counted_output_tokens > self.max_output:
                raise BudgetRejected("TOKEN_LIMIT")
            if current.liability_micro_cny + charge > self.max_micro_cny:
                raise BudgetRejected("COST_LIMIT")
            key = uuid4().hex
            self._requests[key] = (complete_input_tokens, max_counted_output_tokens, charge, "pending")
            return key

    def reconcile(self, key, *, input_tokens=None, output_tokens=None, charge_micro_cny=None):
        with self._lock:
            old = self._requests.get(key)
            if old is None or old[3] != "pending":
                raise BudgetRejected("STATE_CONFLICT")
            values = (input_tokens, output_tokens, charge_micro_cny)
            if any(value is None for value in values):
                self._requests[key] = (*old[:3], "unknown")
                self._unknown = True
                raise BudgetRejected("USAGE_UNKNOWN")
            if (not all(integer(value) for value in values) or any(value > cap for value, cap in zip(values, old[:3]))
                    or charge_micro_cny < self._tariff.liability(input_tokens, output_tokens)):
                # Do not refund an invalid/over-cap usage report or send another request.
                self._requests[key] = (*old[:3], "unknown")
                self._unknown = True
                raise BudgetRejected("USAGE_EXCEEDED_RESERVATION")
            self._requests[key] = (*values, "known")
            self._live()  # Late accounting is retained, but never authorizes a late release.

    def ready(self):
        with self._lock:
            self._live()
            if self._unknown:
                raise BudgetRejected("USAGE_UNKNOWN")
            if self.snapshot().pending_requests:
                raise BudgetRejected("REQUESTS_PENDING")

    def note_failure(self, reason, information_revision):
        with self._lock:
            repeated = self._last_failure == (reason, information_revision)
            self._last_failure = (reason, information_revision)
            if repeated:
                raise BudgetRejected("REPEATED_FAILURE")

    def remediate(self, information_revision):
        with self._lock:
            self.ready()
            if self._last_failure is None:
                raise BudgetRejected("STATE_CONFLICT")
            if self._last_failure[1] == information_revision:
                raise BudgetRejected("REPEATED_FAILURE")
            if self._remediation >= 2:
                raise BudgetRejected("REMEDIATION_EXHAUSTED")
            self._remediation += 1
