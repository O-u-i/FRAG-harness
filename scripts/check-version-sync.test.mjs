import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const source = readFileSync(new URL('./check-version-sync.mjs', import.meta.url), 'utf8').replace(/^import[^\n]+\n/, '');
function check(path, reference = '') {
  const errors = [];
  try {
    runInNewContext(source, {
      readFileSync: (file, encoding) => readFileSync(new URL(`../${file}`, import.meta.url), encoding) + (file === path ? `\n${reference}` : ''),
      console: { log() {}, error: (message) => errors.push(message) },
      process: { exit: (code) => { throw code; } },
    });
    return { code: 0, errors };
  } catch (code) {
    if (typeof code !== 'number') throw code;
    return { code, errors };
  }
}

test('current versions and historical report labels pass', () => {
  assert.equal(check('README.md', 'Historical report: v0.0.0').code, 0);
});
for (const path of ['README.md', 'integrations/vscode/README.md', 'integrations/vscode/bridge/README.md', 'src/agents/README.md']) {
  for (const reference of ['frag-host-0.0.0.zip', 'frag-bridge-0.0.0.vsix', String.raw`FRAG\host\0.0.0`, String.raw`FRAG\\host\\0.0.0`]) {
    test(`${path} rejects stale ${reference}`, () => {
      const result = check(path, reference);
      assert.equal(result.code, 1);
      assert.ok(result.errors.some((message) => message.includes(`stale installation reference ${reference} in ${path}`)));
    });
  }
}
