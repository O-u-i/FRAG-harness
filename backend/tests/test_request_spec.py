"""Shared parsing keeps CLI and model JSON boundaries equally strict."""
import pytest

from frag_api.request_spec import strict_json


@pytest.mark.parametrize("value", [
    '{"a":1,"a":2}', '{"nested":{"a":1,"a":2}}',
    '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}',
    '{"a":1e999}', '{"nested":[-1e999]}', '{} {}', '{"a":',
])
def test_strict_json_rejects_ambiguous_or_nonfinite_input(value):
    with pytest.raises(ValueError):
        strict_json(value)


@pytest.mark.parametrize("encode", [str, lambda text: text.encode("utf-8"),
                                  lambda text: bytearray(text.encode("utf-8"))])
def test_strict_json_preserves_valid_values_and_unicode(encode):
    assert strict_json(encode('{"text":"合成证据","value":1.25,"items":[null,true,42]}')) == {
        "text": "合成证据", "value": 1.25, "items": [None, True, 42],
    }
