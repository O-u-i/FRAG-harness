"""Authenticated loopback consumer of the original VS Code model bridge."""
from urllib.parse import urlsplit
from secrets import token_hex
import httpx
from pydantic import ValidationError
from frag_api.errors import RagNotReadyError, RagFingerprintError, RagOutcomeUnknownError, RagOutputError, RagProviderError
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.agents import BridgeModel
from frag_api.request_spec import strict_json
from frag_api.providers.prepared import output_model_for, verify_prepared


class ModelBridge:
    def __init__(self, address, key):
        parts = urlsplit(address or "")
        if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or not parts.port
                or parts.path or parts.query or parts.fragment or parts.username or parts.password
                or not key or len(key) < 32):
            raise RagNotReadyError()
        self.address, self.key = address, key

    def request(self, path, payload=None, timeout=3):
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout) as client:
                response = client.request("GET" if payload is None else "POST", self.address + path,
                    headers={"Authorization": "Bearer " + self.key}, json=payload)
            if response.status_code == 409:
                raise RagFingerprintError()
            if payload is not None and response.status_code == 502:
                raise RagOutcomeUnknownError()
            if response.status_code == 503:
                raise RagNotReadyError()
            if response.status_code != 200 or len(response.content) > 512 * 1024:
                raise RagProviderError()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            if payload is not None:
                raise RagOutcomeUnknownError() from error
            raise RagNotReadyError() from error
        except (ValueError, TypeError) as error:
            raise RagProviderError() from error

    def models(self):
        try:
            rows = self.request("/models")
            if not isinstance(rows, list) or len(rows) > 200:
                raise ValueError()
            models = [BridgeModel.model_validate(row) for row in rows]
            if len({row.id for row in models}) != len(models):
                raise ValueError()
            return models
        except (ValueError, ValidationError) as error:
            raise RagNotReadyError() from error

    def describe(self, model_id):
        return next((row for row in self.models() if row.id == model_id), None)


class VSCodeProvider:
    def __init__(self, settings):
        self.settings = settings
        self.bridge = ModelBridge(settings.base_url, settings.api_key)

    def execute_prepared(self, call):
        from frag_api.providers.llm import LlmCallResult
        verify_prepared(call, self.settings)
        model = self.bridge.describe(call.model)
        if model is None or model.revision != call.request_binding().get("modelConfigurationRevision"):
            raise RagFingerprintError()
        result = self.bridge.request("/execute", {"modelId": call.model, "revision": model.revision,
            "requestId": token_hex(32), "body": call.request_body()}, timeout=call.timeout_seconds)
        if not isinstance(result, dict) or set(result) != {"text"} or not isinstance(result["text"], str):
            raise RagOutputError()
        try:
            output = output_model_for(call).model_validate(strict_json(result["text"]))
        except (ValueError, ValidationError) as error:
            raise RagOutputError() from error
        return LlmCallResult(output, ProviderUsage())  # Actual billing/usage is not exposed by the stable API.
