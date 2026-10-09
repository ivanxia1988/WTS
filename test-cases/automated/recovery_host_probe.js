// Execute generated page programs in Domi's interpreter; replace only browser IO/transport.
// tabs.foreach orchestration is a small test adapter, not the Electron runner.
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict'), path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const root = process.argv[2];
let state, actions;
const sandbox = {console, URL, structuredClone, setTimeout, clearTimeout,
  crypto: require('crypto').webcrypto,
  browserIO(step, context, resolve) {
    if (step.op === 'page.extract') {
      if (step.id.includes('list-state')) return {...state, route: state.url.split(/[?#]/)[0]};
      if (step.id.includes('read-current-search-page')) return {number: state.page === null ? null : Number(state.page)};
      return {};
    }
    if (step.op === 'page.extract_list') return input.cards.map((r, i) => ({...r, row_index: i}));
    if (step.op === 'page.fill') { actions.fills++; state.query = resolve(step.value, context); }
    if (step.op === 'page.click') {
      if (step.id.endsWith('submit-keyword')) actions.submits++;
      if (step.id.endsWith('collect-candidate-details-open')) {
        const scope = context.scopes[context.scopes.length - 1];
        actions.opens.push(scope.item.candidate_ref);
      }
    }
    return {};
  }
};
vm.createContext(sandbox);
for (const file of ['protocol.js', 'elements.js']) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), sandbox);
let source = fs.readFileSync(path.join(root, 'content.js'), 'utf8');
source = source.slice(0, source.indexOf('  window.addEventListener("message"')) +
  'globalThis.probe = {createContext, executeProgram, resolveTemplate};})();';
source = source.replace('await bridgeInput({kind:"checkpoint"}, context, completing);', '');
source = source.replace('const operation = normalizeOperation(step);\n    if (operation === "page.detect")',
  `const operation = normalizeOperation(step);
    if (operation.startsWith('page.') && !(operation === 'page.wait' && step.until?.type === 'variable'))
      return globalThis.browserIO(step, context, resolveTemplate);
    if (operation === "page.detect")`);
source = source.replace('const target = condition.target || condition.locator;',
  `if (['exists','visible','enabled'].includes(condition.type)) return {matched:false,observations:[]};
    const target = condition.target || condition.locator;`);
vm.runInContext(source, sandbox);
const {createContext, executeProgram} = sandbox.probe;
function context(values, item, index) {
  return createContext({input: {variables: values, scope: {item, index}, limits: {max_loop_iterations: 30}},
    deadline_at: '2100-01-01T00:00:00Z'});
}
async function run(workflow, observed) {
  state = structuredClone(observed); actions = {fills:0, submits:0, opens:[]};
  const c = context({});
  for (const step of workflow.steps) {
    if (step.action === 'page.run') await executeProgram(step.program, c, step.id);
    if (step.action === 'tabs.foreach') {
      const cards = c.values.search.cards;
      for (let i = 0; i < Math.min(step.max_items, cards.length); i++) {
        const child = context(c.values, cards[i], i);
        await executeProgram(step.open.pre_program, child, step.id + '.pre');
        await executeProgram(step.open.program, child, step.id + '.open');
      }
    }
  }
  return actions;
}
(async () => {
  const good = await run(input.normal, input.snapshot);
  assert.equal(good.submits, 0); assert.equal(good.fills, 0);
  assert.deepEqual(good.opens, input.expected);
  const bad = await run(input.normal, {...input.snapshot, query:'changed'});
  assert.equal(bad.submits, 0); assert.equal(bad.fills, 0); assert.equal(bad.opens.length, 0);
  const restored = await run(input.restored, {...input.snapshot, query:'changed'});
  assert.equal(restored.submits, 1); assert.deepEqual(restored.opens, input.expected);
  console.log(JSON.stringify({normal: good, changed: bad, explicitRestore: restored}));
})().catch(e => {console.error(e); process.exitCode = 1;});
