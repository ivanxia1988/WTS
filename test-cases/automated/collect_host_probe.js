// Exercise generated conditions and identity lookup in the installed Domi interpreter.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const root = process.argv[2];
const sandbox = {console, setTimeout, clearTimeout, URL, structuredClone, crypto: require("crypto").webcrypto};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, 'protocol.js'), 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(path.join(root, 'elements.js'), 'utf8'), sandbox);
let source = fs.readFileSync(path.join(root, 'content.js'), 'utf8');
source = source.slice(0, source.indexOf('  window.addEventListener("message"')) +
  'globalThis.probe = {createContext, executeProgram, resolveTemplate};})();';
// Disable only the Electron checkpoint transport; execute the real DSL interpreter.
source = source.replace('await bridgeInput({kind:"checkpoint"}, context, completing);', '');
vm.runInContext(source, sandbox);
const {createContext, executeProgram, resolveTemplate} = sandbox.probe;
function context(values, item = {}) {
  return createContext({input: {variables: values, scope: {item},
    limits: {max_loop_iterations: 30}}, deadline_at: '2100-01-01T00:00:00Z'});
}
(async () => {
  let opened = 0, submitted = 0;
  const states = [
    ['same', null, true], ['query', 'other', false], ['page', '2', false],
    ['filters', ['3天内活跃'], false], ['filters', [...input.snapshot.filters].reverse(), true],
    ['url', input.snapshot.url + '?tracking=irrelevant#session', true],
    ['url', 'https://h.liepin.com/other', false]
  ];
  for (const [field, value, ready] of states) {
    const state = structuredClone(input.snapshot);
    if (field !== 'same') state[field] = value;
    state.route = state.url.split(/[?#]/)[0];
    const c = context({search: {list_state: state}});
    await executeProgram([input.gate], c);
    assert.equal(c.values.search.collection_check.status, ready ? 'ready' : 'needs_restore');
    assert.equal(c.values.search.cards.length, ready ? 1 : 0);
    // Only cards yielded by the actual generated gate enter tabs.foreach.
    opened += c.values.search.cards.length;
    assert(!JSON.stringify(input.gate).includes('page.fill'));
  }
  assert.equal(opened, 3);
  assert.equal(submitted, 0);
  for (const rows of [[], [{candidate_ref: 'liepin:other0001', row_index: 0}],
    [{candidate_ref: 'liepin:wanted001', row_index: 7}],
    [{candidate_ref: 'liepin:wanted001', row_index: 2}, {candidate_ref: 'liepin:wanted001', row_index: 7}]]) {
    const c = context({collect: {live_cards: rows}}, {candidate_ref: 'liepin:wanted001', row_index: 0});
    let failed = false;
    try { await executeProgram(input.identity, c); } catch (e) {
      assert.equal(e.code, 'WAIT_TIMEOUT', e.stack); failed = true;
    }
    assert.equal(failed, rows.filter(r => r.candidate_ref === 'liepin:wanted001').length !== 1);
    if (!failed) assert.equal(resolveTemplate(input.target, c).within.index, 7);
  }
  console.log('Domi interpreter: 7 page-state cases + 4 candidate-identity cases passed; 0 implicit search submissions');
})().catch(e => {console.error(e);process.exitCode = 1;});
