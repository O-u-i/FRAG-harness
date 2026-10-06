"""Synthetic provider and real child-process failures without any model network."""
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from frag_api.errors import (RagFingerprintError, RagIncompleteError, RagNotReadyError,
    RagOutcomeUnknownError, RagOutputError, RagProviderError, RagRefusalError)
from frag_api.providers import pi as pi_provider
from frag_api.providers.llm import LlmSettings, LlmStageSettings, provider_for
from frag_api.providers.pi_process import run_worker_process, worker_ready
from frag_api.providers.prepared import prepare_call, verify_prepared
from frag_api.schemas.rag import RagContextCompression

SETTINGS = LlmStageSettings('openai', 'gpt-4.1-mini', None, 'sk-synthetic-only-not-a-real-key', 5, 'pi')
OUTPUT = {'evidence': [{'evidenceId': 'one', 'summary': 'Synthetic finding',
           'preservedFacts': ['Synthetic finding'], 'uncertainty': []}], 'missingInformation': []}


def context_call(settings=SETTINGS):
    return prepare_call(settings=settings, purpose='context', instructions='Compress selected evidence only.',
        payload={'evidence': []}, output_model=RagContextCompression, max_output_tokens=1500, binding={})


@pytest.mark.parametrize('change', ['lf', 'crlf', 'tampered'])
def test_pi_manifest_accepts_lf_checkout_and_rejects_changed_bytes(monkeypatch, change):
    from frag_api.providers import pi_integrity
    from frag_api.providers.pi_process import WORKER_ROOT
    manifest = WORKER_ROOT / 'vendor/pi-ai/selection-manifest.json'
    read_bytes = Path.read_bytes
    content = manifest.read_bytes().replace(b'\r\n', b'\n')
    if change == 'crlf':
        content = content.replace(b'\n', b'\r\n')
    elif change == 'tampered':
        content += b' '
    monkeypatch.setattr(Path, 'read_bytes', lambda path: content if path == manifest else read_bytes(path))
    if change == 'lf':
        assert pi_integrity.adapter_binding()['selectionManifestHash'] == pi_integrity.MANIFEST_HASH
    else:
        with pytest.raises(RagNotReadyError):
            pi_integrity.adapter_binding()


def test_pi_freezes_wire_and_credentials_are_backend_only(monkeypatch):
    call = context_call()
    captured = []
    def worker(prepared, key):
        captured.append((prepared, key))
        return {'ok': True, 'response': {'status': 'completed', 'outputText': json.dumps(OUTPUT),
            'calls': [], 'usage': {'inputTokens': 150, 'outputTokens': 50}}}
    monkeypatch.setattr(pi_provider, 'execute_worker', worker)
    result = provider_for(SETTINGS).execute_prepared(call)
    assert captured == [(call, SETTINGS.api_key)]
    assert SETTINGS.api_key not in call.model_dump_json()
    assert call.transport == 'pi-responses-v1'
    assert call.request_body()['stream'] is True and call.request_body()['store'] is False
    assert call.request_body_input() == {'evidence': []}
    assert result.output.model_dump(by_alias=True) == OUTPUT and result.usage.input_tokens == 150


@pytest.mark.parametrize('field', ['body', 'binding', 'endpoint', 'model', 'transport'])
def test_pi_prepared_tamper_rejected_before_child(monkeypatch, field):
    call = context_call().model_copy(update={field: '{}'})
    monkeypatch.setattr(pi_provider, 'execute_worker', lambda *_: pytest.fail('Unapproved child dispatch'))
    with pytest.raises(RagFingerprintError):
        provider_for(SETTINGS).execute_prepared(call)


@pytest.mark.parametrize('change', ['provider', 'model', 'endpoint'])
def test_pi_unsupported_route_or_model_fails_before_dispatch(change):
    settings = replace(SETTINGS, **{'provider': 'ollama'} if change == 'provider' else
                       {'model': 'gpt-5-mini'} if change == 'model' else {'base_url': 'http://other.example/v1/'})
    with pytest.raises(RagNotReadyError):
        context_call(settings)


@pytest.mark.parametrize('code,error', [('RAG_REFUSAL', RagRefusalError), ('RAG_INCOMPLETE', RagIncompleteError),
    ('RAG_OUTPUT_INVALID', RagOutputError), ('RAG_PROVIDER_ERROR', RagProviderError),
    ('RAG_OUTCOME_UNKNOWN', RagOutcomeUnknownError), ('UNEXPECTED_CODE', RagOutcomeUnknownError)])
def test_pi_safe_failure_classes(monkeypatch, code, error):
    monkeypatch.setattr(pi_provider, 'execute_worker', lambda *_: {'ok': False, 'errorCode': code})
    with pytest.raises(error):
        provider_for(SETTINGS).execute_prepared(context_call())


@pytest.mark.parametrize('fault', ['partial', 'duplicate', 'nan', 'calls', 'status', 'unknown', 'usage'])
def test_pi_known_malformed_returns_rejected(monkeypatch, fault):
    response = {'status': 'completed', 'outputText': json.dumps(OUTPUT), 'calls': [],
                'usage': {'inputTokens': 10, 'outputTokens': 10}}
    if fault == 'partial': response['outputText'] = '{"evidence":'
    elif fault == 'duplicate': response['outputText'] = '{"evidence":[],"evidence":[],"missingInformation":[]}'
    elif fault == 'nan': response['outputText'] = '{"evidence":[],"missingInformation":[NaN]}'
    elif fault == 'calls': response['calls'] = [{}]
    elif fault == 'status': response['status'] = 'incomplete'
    elif fault == 'unknown': response['privateError'] = 'Synthetic secret'
    else: response['usage']['inputTokens'] = True
    monkeypatch.setattr(pi_provider, 'execute_worker', lambda *_: {'ok': True, 'response': response})
    with pytest.raises(RagOutputError):
        provider_for(SETTINGS).execute_prepared(context_call())


def test_optional_worker_absence_keeps_fake_available(monkeypatch, tmp_path):
    from frag_api.providers import pi_process
    monkeypatch.setattr(pi_process, 'WORKER_ROOT', tmp_path)
    assert worker_ready('gpt-4.1-mini', None) is False
    assert SETTINGS.ready is False
    fake = replace(SETTINGS, provider='fake', adapter='native')
    assert fake.ready is True and provider_for(fake).__class__.__name__ == 'FakeLlmProvider'


@pytest.mark.parametrize('location,name', [('worker', 'wire.mjs'), ('host', 'pi.py'), ('host', '../request_spec.py')])
def test_changed_worker_or_python_adapter_invalidates_old_preview(tmp_path, monkeypatch, location, name):
    from frag_api.providers import pi_integrity
    from frag_api.providers.pi_process import WORKER_ROOT
    provider_root = tmp_path / 'backend' / 'frag_api' / 'providers'
    worker_root = tmp_path / 'backend' / 'pi-worker'
    provider_root.mkdir(parents=True)
    worker_root.mkdir(parents=True)
    original_root = Path(pi_integrity.__file__).parent
    for filename in pi_integrity.HOST_FILES:
        shutil.copyfile(original_root / filename, provider_root / filename)
    for filename in (*pi_integrity.WORKER_FILES, 'package.json', 'package-lock.json', 'vendor/pi-ai/selection-manifest.json'):
        target = worker_root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WORKER_ROOT / filename, target)
    call = context_call()
    monkeypatch.setattr(pi_integrity, '__file__', str(provider_root / 'pi_integrity.py'))
    verify_prepared(call, SETTINGS)
    target = (worker_root if location == 'worker' else provider_root) / name
    comment = '// Synthetic changed mapping.' if location == 'worker' else '# Synthetic changed mapping.'
    target.write_text(target.read_text(encoding='utf-8') + '\n' + comment + '\n', encoding='utf-8')
    with pytest.raises(RagFingerprintError):
        verify_prepared(call, SETTINGS)


def test_adapter_environment_defaults_and_opt_in(monkeypatch):
    for stage in ('CONTEXT', 'INFERENCE', 'RESEARCH'):
        monkeypatch.setenv(f'FRAG_{stage}_LLM_PROVIDER', 'fake')
        monkeypatch.delenv(f'FRAG_{stage}_LLM_ADAPTER', raising=False)
    assert LlmSettings.from_environment().context.adapter == 'native'
    monkeypatch.setenv('FRAG_CONTEXT_LLM_ADAPTER', 'pi')
    with pytest.raises(RagNotReadyError):
        LlmSettings.from_environment()


def test_readiness_emits_only_booleans_and_codes_without_dispatch(monkeypatch, capsys):
    from frag_api.providers import pi_readiness
    monkeypatch.setenv('OPENAI_API_KEY', SETTINGS.api_key)
    monkeypatch.setattr(pi_readiness, 'load_dotenv', lambda *_a, **_k: False)
    monkeypatch.setattr(LlmSettings, 'from_environment', lambda: LlmSettings(SETTINGS, SETTINGS, SETTINGS))
    monkeypatch.setattr(pi_readiness, 'adapter_binding', lambda: {})
    commands = []
    def verify(command, **kwargs):
        commands.append((command, kwargs))
        return type('Result', (), {'returncode': 0, 'stdout': b'{"status":"PASS"}'})()
    monkeypatch.setattr(pi_readiness.subprocess, 'run', verify)
    assert pi_readiness.main() == 0
    printed = capsys.readouterr().out
    assert SETTINGS.api_key not in printed and SETTINGS.model not in printed
    assert all(type(value) is bool for key, value in json.loads(printed).items() if key != 'code')
    assert len(commands) == 1 and commands[0][0][-1].endswith('verify-package.mjs')
    assert 'OPENAI_API_KEY' not in commands[0][1]['env'] and SETTINGS.api_key not in str(commands)


def run_script(tmp_path: Path, source: str, *, timeout=2):
    path = tmp_path / 'synthetic-worker.mjs'
    path.write_text(source, encoding='utf-8')
    executable = shutil.which('node')
    assert executable
    return run_worker_process([str(Path(executable).resolve()), str(path)], b'{}\n', 'a' * 64, timeout, tmp_path)


PRELUDE = "const base={protocolVersion:1,fingerprint:'a'.repeat(64)};const emit=x=>process.stdout.write(JSON.stringify({...base,...x})+'\\n');"


def test_actual_child_protocol_and_environment_isolation(tmp_path, monkeypatch):
    for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'HTTP_PROXY', 'NODE_OPTIONS', 'PI_AUTH_TOKEN', 'USERPROFILE', 'HOME'):
        monkeypatch.setenv(name, 'synthetic-value-not-inherited')
    result = run_script(tmp_path, PRELUDE + "process.stdin.resume();process.stdin.on('end',()=>{"
        "if(['OPENAI_API_KEY','OPENAI_BASE_URL','HTTP_PROXY','NODE_OPTIONS','PI_AUTH_TOKEN','USERPROFILE','HOME'].some(k=>process.env[k]))process.exit(4);"
        "emit({event:'dispatch'});emit({event:'result',ok:true,response:{status:'completed'}});});")
    assert result['ok'] is True and result['response']['status'] == 'completed'


@pytest.mark.parametrize('fault', ['stdout_limit', 'stderr_limit', 'timeout', 'unknown_exit', 'bad_json',
    'wrong_fingerprint', 'no_dispatch', 'double_dispatch', 'wrong_order', 'extra_auth', 'partial'])
def test_actual_child_unknown_outcomes_do_not_retry_or_leak(tmp_path, fault):
    scripts = {
      'stdout_limit': "process.stdout.write('x'.repeat(300000));",
      'stderr_limit': "process.stderr.write('synthetic-private-evidence'.repeat(1000));",
      'timeout': "setTimeout(()=>{},5000);",
      'unknown_exit': "process.exit(3);",
      'bad_json': "process.stdout.write('{not-json}');",
      'wrong_fingerprint': "emit({event:'dispatch'});emit({event:'result',fingerprint:'b'.repeat(64),ok:true,response:{}});",
      'no_dispatch': "emit({event:'result',ok:true,response:{}});",
      'double_dispatch': "emit({event:'dispatch'});emit({event:'dispatch'});emit({event:'result',ok:true,response:{}});",
      'wrong_order': "emit({event:'result',ok:true,response:{}});emit({event:'dispatch'});",
      'extra_auth': "emit({event:'dispatch'});emit({event:'result',ok:true,response:{},apiKey:'synthetic-private-value'});",
      'partial': "process.stdout.write('{\"event\":');",
    }
    with pytest.raises(RagOutcomeUnknownError) as error:
        run_script(tmp_path, PRELUDE + scripts[fault], timeout=0.25 if fault == 'timeout' else 2)
    assert not str(error.value)


def test_known_predispatch_failure_is_preserved(tmp_path):
    result = run_script(tmp_path, PRELUDE + "emit({event:'result',ok:false,errorCode:'RAG_PROVIDER_ERROR',dispatched:false});")
    assert result['ok'] is False and result['dispatched'] is False


def test_fixed_two_stage_path_uses_real_pi_child_with_separate_approvals(client, monkeypatch):
    from frag_api.providers import pi_process
    from test_governance import approve_context, approve_inference
    from test_harness import selection
    service = client.app.state.harness_service
    settings = replace(SETTINGS, api_key='sk-synthetic-worker-key', timeout_seconds=30)
    service.settings = LlmSettings(settings, settings, settings)
    service.flow.settings = service.settings
    service.context_provider = service.inference_provider = provider_for(settings)
    client.app.state.runtime.secret_values = (settings.api_key,)
    original, sent = pi_process.run_worker_process, []
    def fixture(command, payload, fingerprint, timeout, cwd):
        assert len(command) == 2 and Path(command[1]) == pi_process.WORKER_ROOT / 'worker.mjs'
        sent.append(json.loads(payload)['preparedCall'])
        return original([command[0], str(pi_process.WORKER_ROOT / 'tests/host-fixture.mjs')], payload, fingerprint, timeout, cwd)
    monkeypatch.setattr(pi_process, 'run_worker_process', fixture)
    source = selection(client)
    preview = client.post('/api/harness/preview', json=source).json()
    assert sent == [] and isinstance(preview['input'], str)
    first = approve_context(client, source, preview)
    assert first.status_code == 200, first.text
    assert len(sent) == 1 and sent[0] == preview['preparedCall']
    assert isinstance(first.json()['inferencePreview']['input'], str)
    final = approve_inference(client, first.json())
    assert final.status_code == 200, final.text
    assert len(sent) == 2 and sent[1] == first.json()['inferencePreview']['preparedCall']
    assert approve_inference(client, first.json()).status_code == 409 and len(sent) == 2
    report = client.get(f"/api/runtime/runs/{preview['runId']}").json()
    assert report['run']['status'] == 'awaiting_review' and report['semanticReview'] == 'NOT_RUN'
    assert report['consumedTokens'] == 120 and report['toolCalls'] == []
    assert settings.api_key not in json.dumps(report) and settings.api_key not in json.dumps(sent)


@pytest.mark.parametrize('path,stage,tamper', [
    ('startup', 'context', 'missing'), ('startup', 'inference', 'missing'),
    ('resume', 'context', 'missing'), ('resume', 'context', 'mismatched'), ('resume', 'context', 'changed-output')])
def test_new_pi_checkpoint_digest_is_not_legacy_compatible(client, path, stage, tamper):
    from frag_api.schemas.common import ProviderUsage
    from frag_api.schemas.harness import HarnessRequest
    from frag_api.services.runtime_service import RuntimeService
    from test_harness import selection
    service = client.app.state.harness_service
    service.settings = LlmSettings(SETTINGS, SETTINGS, SETTINGS)
    service.flow.settings = service.settings
    source = HarnessRequest.model_validate(selection(client))
    preview = service.preview(source)
    runtime = client.app.state.runtime
    report = runtime.repository.get(preview.run_id)
    attempt = report.requests[0]
    output = RagContextCompression.model_validate({'evidence': [{'evidenceId': row.evidence_id,
        'summary': row.text, 'preservedFacts': [row.text], 'uncertainty': []} for row in preview.candidate_evidence],
        'missingInformation': []})
    runtime.claim(report.run.id, attempt.id, attempt.prepared_call)
    runtime.returned(report.run.id, attempt.id, output, ProviderUsage(inputTokens=10, outputTokens=10))
    if path == 'resume' or stage == 'inference':
        runtime.checkpoint(report.run.id, attempt.id, output, stage='context')
    if stage == 'inference':
        from frag_api.schemas.rag import RagGroundedAnswer
        _, inference, _ = service.flow.resume_preview(report.run.id, source)
        attempt = runtime.repository.get(report.run.id).requests[-1]
        answer = RagGroundedAnswer(answer='Synthetic finding', claims=[{'text':'Synthetic finding',
            'evidenceIds':[output.evidence[0].evidence_id]}], missingInformation=[], disclaimer='Human review required.')
        runtime.claim(report.run.id, attempt.id, inference.prepared_call)
        runtime.returned(report.run.id, attempt.id, answer, ProviderUsage(inputTokens=10, outputTokens=10))
    def corrupt(stored):
        item = next(item for item in stored.requests if item.id == attempt.id)
        if tamper == 'changed-output':
            stored.context.evidence[0].summary = 'A changed persisted statement'
        else:
            item.output_digest = None if tamper == 'missing' else 'f' * 64
    runtime.repository.update(report.run.id, corrupt)
    if path == 'startup':
        RuntimeService(runtime.repository)
        stored = runtime.repository.get(report.run.id)
        assert stored.run.status == 'error' and stored.requests[-1].error_code == 'INVALID_PERSISTED_OUTPUT'
        assert (stored.context is None) if stage == 'context' else (stored.model_output is None)
    else:
        with pytest.raises(RagFingerprintError):
            service.flow.resume_preview(report.run.id, source)
