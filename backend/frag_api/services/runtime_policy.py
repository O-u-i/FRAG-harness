"""Selected read scope, checklist gates, redaction and cumulative request budgets."""
from __future__ import annotations

import re
from dataclasses import dataclass

from frag_api.errors import PolicyRejectedError, RequestBudgetError
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.governance import PreparedCall, SourceBinding, SourceIdentity, TaskContract, ToolDefinition

SECRET = re.compile(r'''(?i)(api[_ -]?key|password|secret|access[_ -]?token|authorization)\s*[:=]\s*(?:bearer\s+)?(?:"[^"\r\n]*"|'[^'\r\n]*'|\S+)''')
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    value = EMAIL.sub("[REDACTED_EMAIL]", KEY.sub("[REDACTED_SECRET]", SECRET.sub("[REDACTED_SECRET]", text)))
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED_SECRET]")
    return value


def configured_secrets(settings) -> tuple[str, ...]:
    return tuple(stage.api_key for stage in (settings.context, settings.inference, getattr(settings, "research", None))
                 if stage is not None and stage.provider in {"openai", "vscode"} and stage.api_key)


def redact_value(value, secrets: tuple[str, ...] = ()):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {key: redact_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact_value(item, secrets) for item in value]
    return value


@dataclass(frozen=True)
class RunBudget:
    limit: int = 30_000
    consumed: int = 0

    def reserve(self, call: PreparedCall) -> None:
        estimated = call.estimated_input_tokens + call.output_limit
        if self.consumed + estimated > self.limit:
            raise RequestBudgetError()

    def charge(self, call: PreparedCall, usage: ProviderUsage) -> "RunBudget":
        count = ((usage.input_tokens if usage.input_tokens is not None else call.estimated_input_tokens)
                 + (usage.output_tokens if usage.output_tokens is not None else call.output_limit))
        updated = RunBudget(self.limit, self.consumed + count)
        if updated.consumed > updated.limit:
            raise RequestBudgetError()
        return updated


class HostPolicy:
    @staticmethod
    def require_task(task: TaskContract) -> None:
        if task.blocking_ids:
            raise PolicyRejectedError()

    @staticmethod
    def require_selected(
        selected: tuple[SourceBinding, ...], identity: SourceIdentity,
        revision: str, locator_ids: tuple[str, ...],
    ) -> SourceBinding:
        matches = [binding for binding in selected if binding.identity == identity]
        if len(matches) != 1 or matches[0].revision != revision:
            raise PolicyRejectedError()
        binding = matches[0]
        if not locator_ids or len(set(locator_ids)) != len(locator_ids) or not set(locator_ids).issubset(binding.locator_ids):
            raise PolicyRejectedError()
        return binding

    @classmethod
    def require_tool(
        cls, tool: ToolDefinition, allowed_tools: frozenset[str], selected: tuple[SourceBinding, ...],
        identity: SourceIdentity, revision: str, locator_ids: tuple[str, ...],
    ) -> SourceBinding:
        if tool.name not in allowed_tools or not tool.read_only or identity.kind not in tool.source_kinds:
            raise PolicyRejectedError()
        return cls.require_selected(selected, identity, revision, locator_ids)
