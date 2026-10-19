'use strict';
// Extension-local scaffolding only. This never authorizes, indexes or reads evidence.
const fs = require('node:fs');
const path = require('node:path');
const MARKER = '<!-- FRAG synthetic acceptance workspace v1 -->';
const README = [MARKER, '# Synthetic acceptance workspace', '',
  'This private per-project folder is for manual Slice A/B checks, not real financial or life-plan data.', '',
  '- sources/synthetic-plan.md is a synthetic plan. Edit it in your editor to test revision changes.',
  '- Authorize only the sources folder explicitly in FRAG Settings; save and build its index manually.',
  '- Search, review the whole file, confirm its exact revision, search again, then read with requireCompletePlan=true.',
  '- Creating this folder does not authorize a source, confirm a plan, read Finance Core, run tests or promote Memory.',
  '- Slice A remains synthetic; production recommendations and Slice C remain unavailable.',
  '- Existing plan edits are preserved. Changing the configured location never moves or deletes this folder.', '',
  'Keep real data, credentials and production databases out of this workspace.', '',
].join('\n');
const PLAN = ['# Synthetic acceptance plan', '', 'Synthetic test only. Not a real personal plan.',
  'BEGIN-PLAN-AB', '', '## Objective', 'Verify complete, revision-bound evidence delivery.', '',
  '## Constraints', 'Do not infer real priorities or authorize financial actions.',
  'Financial facts must come from separately approved FC evidence.', '', '## Counterevidence',
  'This document alone does not establish affordability.', '', 'END-PLAN-AB', '',
].join('\n');
function refuse(code) { throw new Error(code); }
function contains(parent, child) {
  const relative = path.relative(parent, child);
  return relative === '' || (relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative));
}
function localRoot(value) {
  if (typeof value !== 'string' || !path.isAbsolute(value) || value !== value.trim() || /^[/\\]{2}/.test(value) || value.includes('\0')) refuse('ACCEPTANCE_ROOT_INVALID');
  const root = path.resolve(value);
  if (root === path.parse(root).root) refuse('ACCEPTANCE_ROOT_INVALID');
  return root;
}
function inspect(target, directory) {
  let found;
  for (let node = target; ; node = path.dirname(node)) {
    try {
      const info = fs.lstatSync(node);
      if (info.isSymbolicLink() || (node === target && !directory ? !info.isFile() || info.nlink !== 1 : !info.isDirectory())) refuse('ACCEPTANCE_PATH_UNSAFE');
      const actual = fs.realpathSync(node);
      const equal = process.platform === 'win32' ? actual.toLowerCase() === node.toLowerCase() : actual === node;
      if (!equal) refuse('ACCEPTANCE_PATH_UNSAFE');
      if (node === target) found = info;
    } catch (error) { if (error.code !== 'ENOENT') { if (error.message === 'ACCEPTANCE_PATH_UNSAFE') throw error; refuse('ACCEPTANCE_PATH_UNAVAILABLE'); } }
    if (node === path.dirname(node)) break;
  }
  return found;
}
function locations(owned, configured = '') {
  if (!owned || !/^[a-f0-9]{64}$/.test(owned.id)) refuse('ACCEPTANCE_PROJECT_INVALID');
  const state = localRoot(owned.state), project = localRoot(owned.project), installation = localRoot(owned.installation);
  const custom = configured !== '';
  const container = custom ? localRoot(configured) : state;
  const root = custom ? path.join(container, 'projects', owned.id, 'acceptance') : path.join(state, 'acceptance');
  for (const other of [project, installation, ...(custom ? [state] : [])]) {
    if (contains(container, other) || contains(other, container)) refuse('ACCEPTANCE_ROOT_OVERLAP');
  }
  const sourceRoot = path.join(root, 'sources'), planPath = path.join(sourceRoot, 'synthetic-plan.md');
  inspect(root, true); inspect(sourceRoot, true); inspect(planPath, false);
  return { root, sourceRoot, planPath };
}
function workspaceInfo(owned, configured = '') {
  const info = locations(owned, configured), readme = path.join(info.root, 'README.md');
  const owner = inspect(readme, false), plan = inspect(info.planPath, false);
  if (owner && (owner.size > 4096 || !fs.readFileSync(readme, 'utf8').startsWith(MARKER + '\n'))) refuse('ACCEPTANCE_WORKSPACE_NOT_OWNED');
  return { ...info, prepared: Boolean(owner && plan) };
}
function createDirectory(directory) {
  inspect(directory, true);
  try { fs.mkdirSync(directory, { recursive: true }); } catch { refuse('ACCEPTANCE_CREATE_FAILED'); }
  inspect(directory, true);
}
function createFile(file, text) {
  inspect(file, false);
  try { fs.writeFileSync(file, text, { encoding: 'utf8', flag: 'wx', mode: 0o600 }); }
  catch (error) { if (error.code !== 'EEXIST') refuse('ACCEPTANCE_CREATE_FAILED'); }
  inspect(file, false);
}
function prepareWorkspace(owned, configured = '') {
  const info = workspaceInfo(owned, configured);
  if (info.prepared) return info;
  const readme = path.join(info.root, 'README.md');
  // Never adopt an existing folder with unrelated contents or overwrite an edited file.
  if (!inspect(readme, false) && inspect(info.root, true) && fs.readdirSync(info.root).length) refuse('ACCEPTANCE_WORKSPACE_NOT_EMPTY');
  createDirectory(info.root);
  createFile(readme, README);
  workspaceInfo(owned, configured); // Recheck ownership before any nested write.
  createDirectory(info.sourceRoot);
  createFile(info.planPath, PLAN);
  return workspaceInfo(owned, configured);
}
module.exports = { workspaceInfo, prepareWorkspace };
