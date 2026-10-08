'use strict';
const { after } = require('node:test');
const { execFileSync } = require('node:child_process');
const { mkdtempSync } = require('node:fs');
const { resolve, join } = require('node:path');

module.exports = purpose => {
  const script = resolve(__dirname, '../../../../scripts/maintain-tmp.ps1');
  const invoke = args => execFileSync('pwsh', ['-NoProfile', '-File', script, ...args],
    { encoding:'utf8', windowsHide:true, stdio:['ignore','pipe','inherit'] }).trim();
  const root = invoke(['-NewRun', purpose, '-Disposable', '-OwnerProcessId', String(process.pid)]);
  after(() => invoke(['-CloseRun', root]));
  return () => mkdtempSync(join(root, 'case-'));
};
