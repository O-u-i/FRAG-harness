"""Original, deliberately scoped AHP 0.9.0 facade over FRAG's durable runtime."""
import base64
import asyncio
import os
from urllib.parse import urlsplit, unquote
from uuid import UUID
from pydantic import ValidationError
from frag_api.errors import RuntimeConflictError, RuntimeNotFoundError, RagNotReadyError, RagProviderError
from frag_api.schemas.governance import HOST_VERSION
from frag_api.schemas.agents import AgentSession, AgentTurn
from frag_api.schemas.runtime import SessionRecord
from frag_api.services.runtime_service import now, durable_value
from frag_api.services.agent_review import AgentReview

ROOT = "ahp-root://"
WORKSPACE = "file:///frag-workspace"
MODEL = "governed-routes"
EMPTY_CONFIG = {"schema": {"type": "object", "properties": {}}, "values": {}}


class ProtocolError(Exception):
    def __init__(self, code=-32602, message="Unsupported or invalid FRAG carrier request.", data=None):
        self.payload = {"code": code, "message": message}
        if data is not None:
            self.payload["data"] = data


def session_id(uri):
    if not isinstance(uri, str) or not uri.startswith("frag:/"):
        raise ProtocolError()
    try:
        value = UUID(uri[6:])
        if uri != "frag:/" + str(value):
            raise ValueError()
        return value.hex
    except ValueError as error:
        raise ProtocolError() from error


def chat_uri(uri):
    return "ahp-chat://default/" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("=")


class AgentHost(AgentReview):
    def __init__(self, app, review_origin, workspace=WORKSPACE, bridge=None):
        super().__init__(app)
        self.review_origin = review_origin
        self.workspace, self.bridge = workspace, bridge
        self.project_name = app.state.project_name
        self.seq = 0
        self.clients = set()
        self.client_ids = set()
        self.drafts = {}  # Volatile composer state only; never written to runtime storage.

    def is_workspace(self, value):
        """VS Code percent-encodes drive colons; compare only this already-bound root."""
        if not isinstance(value, str):
            return False
        expected, received = urlsplit(self.workspace), urlsplit(value)
        if (received.scheme != "file" or received.netloc != expected.netloc
                or received.query or received.fragment):
            return False
        a, b = unquote(expected.path).rstrip("/"), unquote(received.path).rstrip("/")
        return a.casefold() == b.casefold() if os.name == "nt" else a == b

    def directory_entries(self, value):
        """Virtual ancestry for the native picker; never list/read the actual parents.

        VS Code resolves parent directories while accepting defaultDirectory.
        Only names already contained in the explicitly selected root are exposed.
        Session creation and evidence access remain restricted to that root.
        """
        if not isinstance(value, str):
            return None
        expected, received = urlsplit(self.workspace), urlsplit(value)
        if (received.scheme != "file" or received.netloc != expected.netloc
                or received.query or received.fragment):
            return None
        normalize = str.casefold if os.name == "nt" else lambda path: path
        root = unquote(expected.path).rstrip("/")
        directories = {normalize(root): []}
        while root:
            parent, _, child = root.rpartition("/")
            directories[normalize(parent)] = [{"name": child, "type": "directory"}]
            root = parent
        return directories.get(normalize(unquote(received.path).rstrip("/")))

    def models(self, *, strict=False):
        if self.bridge:
            try:
                return [{"id": row.id, "provider": "frag", "name": row.name,
                         "maxPromptTokens": row.max_input_tokens, "policyState": "enabled"}
                        for row in self.bridge.models()]
            except (RagNotReadyError, RagProviderError) as error:
                if strict:
                    raise ProtocolError(-32000, "The configured VS Code model catalog is unavailable. Check the bridge and saved configuration.") from error
                return []
        config = self.app.state.harness_service.config()
        return [{"id": MODEL, "provider": "frag",
                 "name": f"{config.context.model or 'Context setup needed'} / {config.inference.model or 'Inference setup needed'}",
                 "maxContextWindow": 8192, "maxOutputTokens": 2000,
                 "policyState": "enabled" if config.context.ready and config.inference.ready else "unconfigured"}]

    def selected_model(self, selection, default=None, *, allow_unbound=False):
        if not isinstance(selection, dict) or set(selection) - {"id", "config"} or selection.get("config") not in (None, {}):
            raise ProtocolError(-32602, "Use the saved VS Code model configuration; session overrides are unsupported.")
        # Native provisional creation can precede the composer's model selection.
        if self.bridge and "id" not in selection and allow_unbound:
            return None
        model_id = selection.get("id", (default or MODEL) if not self.bridge else None)
        if not isinstance(model_id, str) or not model_id:
            raise ProtocolError(-32602, "Select a configured VS Code model before sending a task; no model ID was supplied.")
        if model_id not in {row["id"] for row in self.models(strict=True)}:
            raise ProtocolError(-32602, "The selected VS Code model is no longer available in the bound configuration. Refresh the model picker.")
        return model_id

    def root(self):
        return {"agents": [{"provider": "frag", "displayName": "FRAG",
            "description": "Selected evidence with separate Context and Inference approvals",
            "protectedResources": [], "customizations": [], "capabilities": {}, "models": self.models()}],
            "activeSessions": len(self.runtime.repository.agent_sessions()), "terminals": [], "config": EMPTY_CONFIG}

    def carrier_for(self, channel):
        if not isinstance(channel, str):
            raise ProtocolError()
        if channel.startswith("frag:/"):
            return self.current(session_id(channel))
        if channel.startswith("ahp-chat://default/"):
            try:
                encoded = channel.split("/")[-1]
                uri = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
                if chat_uri(uri) != channel:
                    raise ValueError()
                return self.current(session_id(uri))
            except (ValueError, UnicodeError) as error:
                raise ProtocolError() from error
        raise ProtocolError(-32008, "No such FRAG channel.")

    def review_url(self, carrier):
        return f"{self.review_origin}/review?sessionId={carrier.session_id}"

    def content(self, carrier, turn, include_link=True):
        if turn.state == "cancelled":
            return f"Task cancelled. Previous approvals are invalid. Send a new task in this native conversation, then select evidence in [FRAG Review]({self.review_url(carrier)})."
        text = (f"Task saved. Continue in [FRAG Review]({self.review_url(carrier)})." if turn.run_id else
                f"Task saved. Waiting for task configuration in [FRAG Review]({self.review_url(carrier)}). The native reply is complete; no model request has been sent. Open Review in the right-hand Browser tab.") if include_link else ""
        if not turn.run_id:
            return text
        report = self.runtime.repository.get(turn.run_id)
        text += f"\n\nRun `{report.run.id}`: **{report.run.status}**."
        if report.model_output:
            text += "\n\n" + report.model_output.answer
            text += "\n\n" + "\n\n".join(f"{c.text} [{', '.join(c.evidence_ids)}]" for c in report.model_output.claims)
            text += "\n\n" + report.model_output.disclaimer
            text += f"\n\nStructural checks: {report.structural_validation}. Human review: {report.semantic_review}."
        elif report.run.status == "outcome_unknown":
            text += "\n\nThe external outcome is unknown. No automatic resend."
        else:
            text += "\n\nReview the next exact request before approving it."
        return text

    def turn_state(self, carrier, turn):
        parts = [{"kind": "markdown", "id": "frag-" + turn.id,
                  "content": self.content(carrier, turn) if not turn.run_id else f"Task saved. Continue in [FRAG Review]({self.review_url(carrier)})."}]
        if turn.run_id:
            parts.append({"kind": "markdown", "id": "result-" + turn.id,
                          "content": self.content(carrier, turn, include_link=False)})
        value = {"id": turn.id, "startedAt": turn.created_at,
            "message": {"text": turn.text, "origin": {"kind": "user"}, "model": {"id": turn.model_id or carrier.model_id or MODEL}},
            "responseParts": parts}
        # AgentTurn.state belongs to Review. Native Send only delivers the saved-task receipt.
        value.update(state="cancelled" if turn.state == "cancelled" else "complete", duration=0)
        return value

    def summary(self, carrier):
        session = self.runtime.repository.session(carrier.session_id)
        turn = carrier.turns[-1] if carrier.turns else None
        title = turn.text[:80] if turn else session.title
        return {"provider": "frag", "resource": carrier.resource, "title": title,
            "status": 1,
            "workingDirectories": [self.workspace], "defaultChat": chat_uri(carrier.resource),
            "createdAt": session.created_at, "modifiedAt": turn.created_at if turn else session.created_at}

    def snapshot(self, channel):
        if channel == ROOT:
            state = self.root()
        else:
            carrier = self.carrier_for(channel)
            summary = self.summary(carrier)
            chat = {"resource": chat_uri(carrier.resource), "title": summary["title"],
                "status": summary["status"], "modifiedAt": summary["modifiedAt"]}
            if channel == carrier.resource:
                state = {k: summary[k] for k in ("provider", "title", "status", "workingDirectories", "defaultChat")}
                state.update(lifecycle="ready", activeClients=[], chats=[chat], config=EMPTY_CONFIG,
                    customizations=[], changesets=[])
            else:
                state = {**chat, "workingDirectories": [self.workspace], "changesets": [],
                    "turns": [self.turn_state(carrier, t) for t in carrier.turns]}
                if carrier.session_id in self.drafts:
                    state["draft"] = self.drafts[carrier.session_id]
        return {"resource": channel, "state": state, "fromSeq": self.seq}

    async def emit(self, channel, action, origin=None):
        self.seq += 1
        envelope = {"channel": channel, "action": action, "serverSeq": self.seq}
        if origin:
            envelope["origin"] = origin
        await self.publish("action", envelope, channel)

    async def publish(self, method, params, channel=ROOT):
        for client in tuple(self.clients):
            if client.initialized and channel in client.subscriptions:
                if client.queue.full():
                    client.failed = True
                else:
                    client.queue.put_nowait({"jsonrpc": "2.0", "method": method, "params": params})

    async def create(self, params):
        directories = params.get("workingDirectories")
        if (params.get("provider") != "frag" or not isinstance(directories, list)
                or len(directories) != 1 or not self.is_workspace(directories[0])
                or params.get("config") not in (None, {})):
            raise ProtocolError()
        model_id = self.selected_model(params.get("model", {}), allow_unbound=True)
        uri = params["channel"]
        sid = session_id(uri)
        with self.lock:
            try:
                old = self.current(sid)
                if old.resource != uri or (model_id and old.model_id and old.model_id != model_id):
                    raise ProtocolError()
                return
            except RuntimeNotFoundError:
                pass
            self.runtime.repository.create_agent_session(SessionRecord(id=sid, title="FRAG evidence review", createdAt=now()),
                AgentSession(sessionId=sid, resource=uri, modelId=model_id))
        await self.publish("root/sessionAdded", {"channel": ROOT, "summary": self.summary(self.current(sid))})

    async def dispatch(self, client, params):
        action, channel = params.get("action", {}), params.get("channel", "")
        kind = action.get("type")
        origin = {"clientId": client.client_id, "clientSeq": params["clientSeq"]}
        if kind == "root/configChanged" and channel == ROOT and not action.get("config"):
            await self.emit(channel, action, origin)
            return
        carrier = self.carrier_for(channel)
        if kind == "chat/turnStarted" and channel == chat_uri(carrier.resource):
            message = action.get("message", {})
            if not isinstance(message, dict) or not isinstance(message.get("origin"), dict):
                raise ProtocolError(-32602, "Invalid task message format. Send a user text message from the native composer.")
            text = message.get("text")
            turn_id = action.get("turnId")
            if (not isinstance(text, str) or message["origin"].get("kind") != "user"
                    or not isinstance(turn_id, str) or not 1 <= len(turn_id) <= 128
                    or not isinstance(message.get("attachments", []), list)):
                raise ProtocolError(-32602, "Invalid task message format. Send a user text message with a valid turn ID and attachment list.")
            if not 3 <= len(text.strip()) <= 500:
                raise ProtocolError(-32602, "Task text must contain 3–500 characters after trimming whitespace.")
            if message.get("attachments"):
                raise ProtocolError(-32602, "Native Context attachments cannot be submitted as evidence. Remove them from the composer, resend the task, then select evidence in FRAG Review. Attachment contents were not read.")
            model_id = self.selected_model(message.get("model", {}), carrier.model_id)
            safe = durable_value(text.strip(), self.runtime.redaction_secrets)
            with self.lock:
                carrier = self.current(carrier.session_id)
                duplicate = next((t for t in carrier.turns if t.id == turn_id), None)
                if duplicate:
                    if duplicate.text != safe or (duplicate.model_id and duplicate.model_id != model_id):
                        raise ProtocolError(-32000, "This turn ID already belongs to a different saved task. Send a new native message.")
                    return  # Durable replay is observation, never execution.
                if len(carrier.turns) >= 200:
                    raise ProtocolError(-32000, "This session has reached its 200-task limit. Start a new native FRAG session.")
                if carrier.turns and carrier.turns[-1].state == "running":
                    previous = carrier.turns[-1]
                    if previous.run_id and self.runtime.repository.get(previous.run_id).run.status == "outcome_unknown":
                        raise ProtocolError(-32000, "The previous task has an unknown external outcome. Reconcile it in FRAG Review before starting another task.")
                    self.cancel(carrier.session_id, previous.id)
                self.discard_preview(carrier.session_id)
                def append(value):
                    value.model_id = model_id
                    value.turns.append(AgentTurn(id=turn_id, text=safe, createdAt=now(), modelId=model_id))
                carrier = self.runtime.repository.update_agent_session(carrier.session_id, append)
                self.drafts.pop(carrier.session_id, None)
            accepted = {"type": kind, "turnId": turn_id, "startedAt": carrier.turns[-1].created_at,
                "message": {"text": safe, "origin": {"kind": "user"}, "model": {"id": model_id}}}
            await self.emit(channel, accepted, origin)
            await self.emit(channel, {"type": "chat/responsePart", "turnId": turn_id,
                "part": {"kind": "markdown", "id": "frag-" + turn_id, "content": self.content(carrier, carrier.turns[-1])}})
            await self.emit(channel, {"type": "chat/turnComplete", "turnId": turn_id, "duration": 0})
            await self.emit(channel, {"type": "chat/activityChanged"})
            await self.publish("root/sessionSummaryChanged", {"channel": ROOT, "session": carrier.resource,
                "changes": {"title": safe[:80], "status": 1, "modifiedAt": now()}})
        elif kind == "chat/turnCancelled" and channel == chat_uri(carrier.resource):
            carrier = await asyncio.to_thread(self.cancel, carrier.session_id, action.get("turnId"))
            await self.emit(channel, {"type": kind, "turnId": action["turnId"], "duration": 0}, origin)
            await self.emit(channel, {"type": "chat/activityChanged"})
        elif kind == "session/activeClientSet" and channel == carrier.resource:
            # Native tools/skills are descriptors, never source access or executable bindings.
            active = action.get("activeClient", {})
            if active.get("clientId") != client.client_id:
                raise ProtocolError()
            await self.emit(channel, {"type": kind, "activeClient": {
                "clientId": client.client_id, "tools": [], "customizations": []}}, origin)
        elif kind == "session/isReadChanged" and channel == carrier.resource:
            await self.emit(channel, {"type": kind, "isRead": bool(action.get("isRead"))}, origin)
        elif kind == "chat/draftChanged" and channel == chat_uri(carrier.resource):
            # Acknowledge the exact edit; attachment descriptors are never dereferenced.
            if action.get("draft") is None:
                self.drafts.pop(carrier.session_id, None)
            else:
                self.drafts[carrier.session_id] = action["draft"]
            await self.emit(channel, action, origin)
        elif kind == "session/configChanged" and channel == carrier.resource and not action.get("config"):
            await self.emit(channel, {"type": kind, "config": {}}, origin)
        else:
            raise ProtocolError(-32601, "This action is not supported by the governed FRAG carrier.")


class AgentConnection:
    def __init__(self, host):
        self.host = host
        self.initialized = False
        self.client_id = ""
        self.subscriptions = set()
        self.queue = asyncio.Queue(maxsize=100)
        self.failed = False

    def restore_subscriptions(self, resources):
        if not isinstance(resources, list) or len(resources) > 200 or any(not isinstance(c, str) for c in resources):
            raise ProtocolError()
        snapshots = []
        for resource in dict.fromkeys(resources):
            try:
                snapshots.append(self.host.snapshot(resource))
            except (RuntimeNotFoundError, ProtocolError):
                if resource == ROOT or resource.startswith(("frag:/", "ahp-chat://default/")):
                    continue
                raise ProtocolError()
        self.subscriptions = {snapshot["resource"] for snapshot in snapshots}
        return snapshots

    async def request(self, method, params):
        if method == "initialize":
            if self.initialized or params.get("channel") != ROOT:
                raise ProtocolError()
            if "0.9.0" not in params.get("protocolVersions", []):
                raise ProtocolError(-32005, "FRAG supports AHP 0.9.0 only.", {"supportedVersions": ["0.9.0"]})
            client_id = params.get("clientId")
            if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
                raise ProtocolError()
            snapshots = self.restore_subscriptions(params.get("initialSubscriptions", [ROOT]))
            self.client_id, self.initialized = client_id, True
            self.host.client_ids.add(client_id)
            return {"protocolVersion": "0.9.0", "serverSeq": self.host.seq,
                "serverInfo": {"name": "FRAG", "version": HOST_VERSION}, "defaultDirectory": self.host.workspace,
                "snapshots": snapshots}
        if method == "reconnect":
            client_id = params.get("clientId")
            if not isinstance(client_id, str) or params.get("channel", ROOT) != ROOT or self.initialized:
                raise ProtocolError()
            if client_id not in self.host.client_ids:
                # Native clients respond to NotFound with a version-negotiated fresh initialize.
                raise ProtocolError(-32008, "Initialize a fresh connection after FRAG host restart.")
            if type(params.get("lastSeenServerSeq")) is not int or params["lastSeenServerSeq"] < 0:
                raise ProtocolError()
            snapshots = self.restore_subscriptions(params.get("subscriptions"))
            self.client_id, self.initialized = client_id, True
            return {"type": "snapshot", "snapshots": snapshots}
        if not self.initialized:
            raise ProtocolError(-32000, "Initialize the FRAG carrier first.")
        channel = params.get("channel", "")
        if not isinstance(channel, str):
            raise ProtocolError()
        if method == "subscribe":
            value = self.host.snapshot(channel)
            self.subscriptions.add(channel)
            return {"snapshot": value}
        if method == "unsubscribe":
            self.subscriptions.discard(channel)
            return None
        if method == "dispatchAction":
            if not isinstance(params.get("clientSeq"), int) or not isinstance(params.get("action"), dict):
                raise ProtocolError()
            await self.host.dispatch(self, params)
            return None
        if method == "createSession":
            return await self.host.create(params)
        if method in ("createTerminal", "writeTerminal", "resizeTerminal", "disposeTerminal"):
            raise ProtocolError(-32601, "FRAG does not provide terminals or native coding tools.")
        if channel != ROOT:
            raise ProtocolError()
        if method == "listSessions":
            return {"items": [self.host.summary(c) for c in self.host.runtime.repository.agent_sessions()]}
        if method == "resolveSessionConfig" and params.get("provider") == "frag":
            if params.get("config") not in (None, {}):
                raise ProtocolError()
            return EMPTY_CONFIG
        if method == "sessionConfigCompletions":
            return {"items": []}
        if method in ("resourceRead", "resourceResolve", "resourceList") and not isinstance(params.get("uri"), str):
            raise ProtocolError()
        if method in ("resourceResolve", "resourceList"):
            entries = self.host.directory_entries(params.get("uri"))
            if entries is not None:
                return {"type": "directory"} if method == "resourceResolve" else {"entries": entries}
        if method in ("resourceRead", "resourceResolve", "resourceList"):
            raise ProtocolError(-32008, "Only the bound project root is advertised; select file content in FRAG Review.")
        if method == "ping":
            return {}
        raise ProtocolError(-32601, "FRAG does not provide terminals, file writes or native coding tools.")
