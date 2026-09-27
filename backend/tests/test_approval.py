from frag_api.services import approval


def test_approval_expires_and_is_single_use(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(approval.time, "monotonic", lambda: now[0])
    registry = approval.ApprovalRegistry(ttl_seconds=600)
    token = registry.issue("fingerprint")
    assert registry.consume(token, "fingerprint")
    assert not registry.consume(token, "fingerprint")
    expired = registry.issue("fingerprint")
    now[0] = 701.0
    assert not registry.consume(expired, "fingerprint")


def test_pending_inference_expires_and_is_single_use(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(approval.time, "monotonic", lambda: now[0])
    registry = approval.PendingInferenceRegistry(ttl_seconds=600)
    token = registry.issue("fingerprint", {"synthetic": True})
    assert registry.consume(token, "fingerprint") == {"synthetic": True}
    assert registry.consume(token, "fingerprint") is None
    expired = registry.issue("fingerprint", {"synthetic": True})
    now[0] = 701.0
    assert registry.consume(expired, "fingerprint") is None
