"""Build a redacted, version-bound Context preview for both fixed workflow sources."""
from frag_api.providers.llm import LlmSettings, context_input, inference_input
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.providers.prepared import prepare_call, stage_route
from frag_api.schemas.common import TokenBudget
from frag_api.schemas.governance import SourceBinding, TaskContract
from frag_api.schemas.rag import RagContextCompression, RagEvidence, RagGroundedAnswer
from frag_api.services.governed_context import CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT
from frag_api.services.runtime_policy import configured_secrets, redact_value


def context_preview_fields(*, settings: LlmSettings, evidence: list[RagEvidence], goal: str,
                           task: TaskContract, sources: tuple[SourceBinding, ...], selection_hash: str,
                           loop_definition: dict, redaction_secrets: tuple[str, ...] = ()) -> dict:
    instructions, payload = context_input(evidence)
    payload.update(goal=goal, task=task.model_dump(by_alias=True))
    secrets = configured_secrets(settings) + redaction_secrets
    sources = tuple(SourceBinding.model_validate(redact_value(source.model_dump(by_alias=True), secrets)) for source in sources)
    inference_instructions, _ = inference_input(RagContextCompression(evidence=[], missingInformation=[]), "")
    call = prepare_call(
        settings=settings.context, purpose="context", instructions=instructions,
        payload=redact_value(payload, secrets), output_model=RagContextCompression,
        max_output_tokens=CONTEXT_OUTPUT_LIMIT,
        binding=redact_value({"selectionHash": selection_hash,
                              "sources": [source.model_dump(by_alias=True) for source in sources],
                              "task": task.model_dump(by_alias=True),
                              "loop": loop_definition,
                              "inferenceContract": {"instructionsHash":fingerprint(inference_instructions),
                                  "outputSchemaHash":fingerprint(RagGroundedAnswer.model_json_schema(by_alias=True)),
                                  "outputLimit":INFERENCE_OUTPUT_LIMIT},
                              "inferenceRoute": stage_route(settings.inference)}, secrets),
    )
    body = call.request_body()
    return {"candidateEvidence": [RagEvidence.model_validate(item) for item in call.request_body_input()["evidence"]],
            "instructions": body["instructions"], "input": body["input"] if isinstance(body["input"], str) else canonical_json(body["input"]),
            "preparedCall": call, "sourceBindings": sources,
            "task": TaskContract.model_validate(redact_value(task.model_dump(by_alias=True), secrets)),
            "canApprove": bool(evidence) and not task.blocking_ids, "contextFingerprint": call.fingerprint, "approvalToken": "",
            "budget": TokenBudget(estimatedInputTokens=call.estimated_input_tokens,
                                  inputBudget=call.input_budget, reservedPercent=call.reserved_percent,
                                  contextOutputLimit=CONTEXT_OUTPUT_LIMIT, inferenceOutputLimit=INFERENCE_OUTPUT_LIMIT)}
