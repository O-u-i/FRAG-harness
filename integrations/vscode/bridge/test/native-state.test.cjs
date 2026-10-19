'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm');
const { readFileSync } = require('node:fs');
const { join, resolve, parse } = require('node:path');

function launcher({ linked, file } = {}) {
  const module = { exports: {} };
  vm.runInNewContext(readFileSync(join(__dirname, '../host-launcher.cjs'), 'utf8'), {
    module, process, require(name) {
      if (name === 'node:fs') return {
        realpathSync: resolve,
        lstatSync: path => ({ isSymbolicLink: () => path === linked, isDirectory: () => path !== file }),
      };
      return require(name);
    },
  });
  return module.exports;
}

test('private state roots retain project isolation without moving or creating files', () => {
  const setting = JSON.parse(readFileSync(join(__dirname, '../package.json'), 'utf8')).contributes.configuration.properties['frag.privateStateRoot'];
  assert.equal(setting.scope, 'machine');
  assert.equal(setting.default, '');
  const { stateDirectory, projectIdentity } = launcher();
  const project = resolve('synthetic/project'), installation = resolve('synthetic/host');
  const standard = resolve('synthetic/globalStorage'), custom = resolve('synthetic/private disk');
  assert.equal(stateDirectory(standard, project, installation), join(standard, 'projects', projectIdentity(project)));
  assert.equal(stateDirectory(custom, project, installation), join(custom, 'projects', projectIdentity(project)));
  assert.notEqual(stateDirectory(custom, resolve('synthetic/other-project'), installation), stateDirectory(custom, project, installation));
  for (const invalid of ['', 'relative/state', '\\\\server\\share', '//server/share', parse(custom).root,
    project, join(project, 'state'), resolve('synthetic'), installation, join(installation, 'state')]) {
    assert.throws(() => stateDirectory(invalid, project, installation), /PRIVATE_STATE_ROOT_INVALID/);
  }
});

test('linked roots, project-state children and non-directory ancestors refuse before writing', () => {
  const project = resolve('synthetic/project'), installation = resolve('synthetic/host');
  const storage = resolve('synthetic/private'), state = join(storage, 'projects', launcher().projectIdentity(project));
  for (const linked of [storage, join(storage, 'projects'), state]) {
    assert.throws(() => launcher({ linked }).stateDirectory(storage, project, installation), /PRIVATE_STATE_ROOT_INVALID/);
  }
  assert.throws(() => launcher({ file: storage }).stateDirectory(storage, project, installation), /PRIVATE_STATE_ROOT_INVALID/);
});
