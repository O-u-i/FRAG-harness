"""Native folder acceptance with virtual ancestry and no outside filesystem access."""
from uuid import uuid4
from frag_api.services.agent_host import ROOT
from test_agent_host import client_for, initialize, rpc
from test_runtime_recovery import CountingProvider, app_for


def test_native_picker_can_resolve_ancestry_but_lists_only_the_bound_path(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        client.app.state.agent_host.workspace = "file:///S:/Synthetic/Chosen"
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            for uri, name in [("file:///", "S:"), ("file:///S%3A/", "Synthetic"),
                              ("file:///S%3A/Synthetic/", "Chosen")]:
                assert rpc(socket, "resourceResolve", {"channel": ROOT, "uri": uri})["result"] == {"type": "directory"}
                assert rpc(socket, "resourceList", {"channel": ROOT, "uri": uri})["result"] == {
                    "entries": [{"name": name, "type": "directory"}]}
            assert rpc(socket, "resourceList", {"channel": ROOT, "uri": "file:///S:/Synthetic/Chosen/"})["result"] == {"entries": []}
            # Ancestors are metadata only, never valid session roots or readable evidence.
            for uri in ["file:///S:/Synthetic", "file:///S:/Synthetic/Sibling", "file:///S:/Other",
                        "file:///S:/Synthetic/Chosen/private.txt", "file:///S:/Synthetic/Chosen/../Sibling",
                        "file://other/S:/Synthetic/Chosen", "file:///S:/Synthetic/Chosen?query=1",
                        "file:///S:/Synthetic/Chosen#fragment", "https://example.invalid/Chosen"]:
                assert "error" in rpc(socket, "resourceRead", {"channel": ROOT, "uri": uri})
                assert "error" in rpc(socket, "createSession", {"channel": "frag:/" + str(uuid4()),
                    "provider": "frag", "workingDirectories": [uri]})
            for uri in ["file:///S:/Other", "file:///S:/Synthetic/Sibling", "file:///S:/Synthetic/Chosen/private.txt",
                        "file:///S:/Synthetic/Chosen/../Sibling", "file://other/S:/Synthetic/Chosen",
                        "file:///S:/Synthetic/Chosen?query=1", "file:///S:/Synthetic/Chosen#fragment"]:
                for method in ["resourceList", "resourceResolve"]:
                    assert "error" in rpc(socket, method, {"channel": ROOT, "uri": uri})
            assert "error" not in rpc(socket, "createSession", {"channel": "frag:/" + str(uuid4()),
                "provider": "frag", "workingDirectories": ["file:///S:/Synthetic/Chosen"]})
        assert provider.calls == []
