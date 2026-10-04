"""Freeze configured routes and the Sol profile without credentials or model calls."""
from dataclasses import replace

import pytest

from frag_api.errors import RagFingerprintError, RagNotReadyError
from frag_api.providers.pi_process import configured_endpoint, worker_ready
from frag_api.providers.prepared import verify_prepared
from frag_api.request_spec import canonical_json, estimated_tokens, fingerprint
from test_pi_provider import SETTINGS, context_call


@pytest.mark.parametrize('base', [None, 'https://api.openai.com/v1', 'https://relay.example/v1/'])
def test_pi_route_is_explicitly_frozen_and_model_bound(base):
    settings = replace(SETTINGS, model='gpt-6.1-sol', base_url=base)
    call = context_call(settings)
    verify_prepared(call, settings)
    assert call.endpoint == configured_endpoint(base)
    assert call.request_body()['reasoning'] == {'effort': 'low'}
    assert call.request_body()['include'] == ['reasoning.encrypted_content']
    assert call.request_binding()['nativeReplayVersion'] == 2
    assert call.request_body()['max_output_tokens'] == 1500
    assert call.timeout_seconds == 5 and call.max_retries == 0
    assert SETTINGS.api_key not in call.model_dump_json()
    with pytest.raises(RagFingerprintError):
        verify_prepared(call, replace(settings, base_url='https://different.example/v1/'))


@pytest.mark.parametrize('base', [
    'http://relay.example/v1', 'https://name:password@relay.example/v1',
    'https://relay.example:443/v1', 'https://relay.example:8443/v1',
    'https://RELAY.example/v1', 'https://relay.example/v1?route=other',
    'https://relay.example/v1?', 'https://relay.example/v1#',
    'https://relay.example/v1/../v1', 'https://relay.example/%76%31',
    'https://relay.example/v1\\', ' https://relay.example/v1',
    'https://relay..example/v1', 'https://relay.example./v1',
    'https://-relay.example/v1', 'https://relay.example',
    'https://relay.example/v1/responses', 'https://rel\u00e4y.example/v1',
])
def test_pi_ambiguous_or_unapproved_route_shape_fails_before_dispatch(base):
    assert worker_ready('gpt-6.1-sol', base) is False
    with pytest.raises(RagNotReadyError):
        context_call(replace(SETTINGS, model='gpt-6.1-sol', base_url=base))


@pytest.mark.parametrize('fault', ['effort', 'include', 'binding'])
def test_pi_sol_profile_rejects_a_rehashed_but_invalid_request(fault):
    settings = replace(SETTINGS, model='gpt-6.1-sol')
    call = context_call(settings)
    body, binding = call.request_body(), call.request_binding()
    if fault == 'effort': body['reasoning'] = {'effort': 'none'}
    elif fault == 'include': body['include'] = []
    else: binding['nativeReplayVersion'] = 1
    spec = call.model_dump(by_alias=True, exclude={'fingerprint'})
    spec.update(body=canonical_json(body), binding=canonical_json(binding), estimatedInputTokens=estimated_tokens(body))
    # A fingerprint alone never authorizes an unsupported wire/replay profile.
    changed = type(call)(**spec, fingerprint=fingerprint(spec))
    with pytest.raises(RagFingerprintError):
        verify_prepared(changed, settings)
