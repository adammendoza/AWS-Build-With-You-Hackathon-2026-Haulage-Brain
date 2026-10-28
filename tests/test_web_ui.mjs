// Run with: node --test tests/test_web_ui.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/load_quoting_swarm/web_assets/app.js', import.meta.url), 'utf8');
const MANAGER_KEY = 'haulage-brain-manager';

function app({ storage = new Map(), blocked = false, mode = 'server' } = {}) {
  const elements = new Map();
  let ready;
  const requests = [];
  const element = (selector) => {
    if (!elements.has(selector)) elements.set(selector, {
      value: selector === '#sort' ? 'pickup' : '',
      checked: false, textContent: '', innerHTML: '', listeners: {},
      addEventListener(name, listener) { this.listeners[name] = listener; },
      firstChild: { textContent: '' },
      insertAdjacentHTML() {}, replaceChildren() {}, append() {},
      showModal() {}, close() {}, blur() {},
    });
    return elements.get(selector);
  };
  const context = vm.createContext({
    document: { querySelector: element, querySelectorAll: () => [], addEventListener: (name, listener) => { if (name === 'DOMContentLoaded') ready = listener; } },
    localStorage: {
      getItem(key) { if (blocked) throw new Error('Storage blocked'); return storage.get(key) ?? null; },
      setItem(key, value) { if (blocked) throw new Error('Storage blocked'); storage.set(key, value); },
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, json: async () => options?.method
        ? { status: 'BOOKED', manager: JSON.parse(options.body).manager }
        : { deployment: { mode }, loads: [], summary: { loads: 0, available: 0 } } };
    },
    setTimeout() {}, clearTimeout() {},
  });
  vm.runInContext(source, context);
  return { element, requests, storage, ready: () => ready(), run: (code) => vm.runInContext(code, context) };
}

test('manager name survives reload before the input loses focus', async () => {
  const first = app();
  await first.ready();
  assert.equal(first.element('#manager').value, '');
  first.element('#manager').value = 'Taylor';
  first.element('#manager').listeners.input();
  assert.equal(first.element('#manager-status').textContent, 'Name saved');
  const reloaded = app({ storage: first.storage });
  await reloaded.ready();
  assert.equal(reloaded.element('#manager').value, 'Taylor');
});

test('Enter commits a trimmed name and blank names use the default', async () => {
  const ui = app();
  await ui.ready();
  ui.element('#manager').value = '  Taylor  ';
  let prevented = false;
  ui.element('#manager').listeners.keydown({ key: 'Enter', preventDefault() { prevented = true; }, target: ui.element('#manager') });
  assert.ok(prevented);
  assert.equal(ui.element('#manager').value, 'Taylor');
  ui.element('#manager').value = '   ';
  ui.element('#manager').listeners.change();
  assert.equal(ui.element('#manager').value, '');
  assert.equal(ui.storage.get(MANAGER_KEY), '');
  assert.equal(ui.run('managerName()'), 'Fleet Manager');
});

test('blocked storage still loads the board and submits the current manager', async () => {
  const ui = app({ blocked: true });
  await ui.ready();
  assert.match(ui.element('#result-count').textContent, /0 of 0 loads/);
  ui.element('#manager').value = 'Taylor';
  ui.element('#manager').listeners.input();
  assert.equal(ui.element('#manager-status').textContent, 'Name stays in this tab');
  await ui.run('state.pending = { loadId: "TEST-1", decision: "APPROVE" }; decide()');
  const request = ui.requests.find(({ options }) => options?.method);
  assert.equal(JSON.parse(request.options.body).manager, 'Taylor');
});

test('static decisions preserve the manager and show attribution safely', async () => {
  const ui = app({ mode: 'static-demo' });
  await ui.ready();
  ui.element('#manager').value = 'Taylor <Fleet>';
  await ui.run('state.pending = { loadId: "TEST-1", decision: "PASS" }; decide()');
  const decisions = JSON.parse(ui.storage.get('haulage-brain-demo-decisions'));
  assert.equal(decisions['Q-TEST-1'].manager, 'Taylor <Fleet>');
  ui.run('state.loads = [{ load_id: "TEST-1", status: "Available", quote_analysis: {}, ledger: { status: "PASSED", manager: "Taylor <Fleet>" } }]; state.filtered = state.loads; state.selectedId = "TEST-1"; renderInspector()');
  assert.match(ui.element('#inspector').innerHTML, /Passed by Taylor &lt;Fleet&gt;/);
});

test('unreadable demo storage cannot prevent initialization', async () => {
  for (const value of ['{broken', 'null', '[]']) {
    const ui = app({ mode: 'static-demo', storage: new Map([['haulage-brain-demo-decisions', value]]) });
    await ui.ready();
    assert.match(ui.element('#result-count').textContent, /0 of 0 loads/);
  }
  const ui = app({ blocked: true, mode: 'static-demo' });
  await ui.ready();
  assert.match(ui.element('#result-count').textContent, /0 of 0 loads/);
});
