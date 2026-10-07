'use strict';

// Original diagnostic extension. It deliberately has no network or backend client.
const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');

const TYPE = 'frag-offline';
const PARTICIPANT = 'frag-local.offline';

function activate(context) {
  const output = vscode.window.createOutputChannel('FRAG compatibility');
  context.subscriptions.push(output);
  const receipt = {
    schemaVersion: 1,
    extensionVersion: '0.0.1',
    vscodeVersion: vscode.version,
    activated: true,
    controllerRegistered: false,
    contentProviderRegistered: false,
    contentRequests: 0,
    handledMessages: 0,
    modelApiAvailable: false,
    generatedSessionCommands: [],
    nativeSessionAttempt: 'NOT_RUN',
    nativeAgentsAcceptance: 'UNVERIFIED',
    errors: [],
  };
  const receiptFile = process.env.FRAG_VSCODE_PROBE_RECEIPT;
  function record() {
    output.appendLine(JSON.stringify(receipt));
    // Receipt writes are restricted to an explicitly configured, ignored test directory.
    if (receiptFile && path.isAbsolute(receiptFile) &&
        receiptFile.endsWith(`${path.sep}extension-receipt.json`) &&
        receiptFile.split(path.sep).includes('.tmp')) {
      fs.writeFileSync(receiptFile, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');
    }
  }

  const handler = async (request, chatContext, stream, cancellation) => {
    if (cancellation.isCancellationRequested) return {};
    receipt.handledMessages += 1;
    // The model object selected by VS Code is never invoked, and attachments are ignored.
    stream.markdown('FRAG offline handler received the test message. No model was called.');
    record();
    return { metadata: { offline: true } };
  };

  try {
    const participant = vscode.chat.createChatParticipant(PARTICIPANT, handler);
    context.subscriptions.push(participant);
    const controller = vscode.chat.createChatSessionItemController(TYPE, async () => {});
    controller.newChatSessionItemHandler = async () => {
      const resource = vscode.Uri.from({ scheme: TYPE, path: `/session/${Date.now()}` });
      const item = controller.createChatSessionItem(resource, 'FRAG offline session');
      item.status = vscode.ChatSessionStatus.NeedsInput;
      record();
      return item;
    };
    context.subscriptions.push(controller);
    receipt.controllerRegistered = true;
    context.subscriptions.push(vscode.chat.registerChatSessionContentProvider(TYPE, {
      provideChatSessionContent() {
        receipt.contentRequests += 1;
        record();
        return { title: 'FRAG offline session', history: [], requestHandler: handler };
      },
    }, participant));
    receipt.contentProviderRegistered = true;
  } catch (error) {
    receipt.errors.push(String(error?.message || error));
  }

  context.subscriptions.push(vscode.commands.registerCommand('frag.probe.inspect', async () => {
    receipt.generatedSessionCommands = (await vscode.commands.getCommands(true))
      .filter(command => command.includes(TYPE));
    record();
    output.show(true);
    return { ...receipt };
  }));
  context.subscriptions.push(vscode.commands.registerCommand('frag.probe.newSession', async () => {
    receipt.nativeSessionAttempt = 'REQUESTED';
    record();
    try {
      // Exercise the contributed command in this Agents window. Do not open an editor fallback.
      await vscode.commands.executeCommand(`workbench.action.chat.openNewChatSessionInPlace.${TYPE}`, 'sidebar');
      receipt.nativeSessionAttempt = 'COMMAND_RETURNED_UNVERIFIED';
    } catch (error) {
      receipt.nativeSessionAttempt = 'REJECTED';
      receipt.errors.push(String(error?.message || error));
    }
    record();
  }));
  record();
  vscode.commands.getCommands(true).then(commands => {
    receipt.generatedSessionCommands = commands.filter(command => command.includes(TYPE));
    record();
  });
}

module.exports = { activate };
