const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(
  path.join(__dirname, "../src/load_quoting_swarm/web_assets/easter-eggs.js"),
  "utf8",
);

// Exercise the real renderer with a controllable clock and browser lifecycle.
function workspace({ reduced = false, fine = true, width = 1440 } = {}) {
  const frames = new Map(), observers = [], media = [], draws = [];
  let now = 0, nextFrame = 0, dialogOpen = false;
  function element(rect = {}) {
    return {
      dataset: {}, events: {}, style: { setProperty() {} },
      addEventListener(name, callback) { this.events[name] = callback; },
      getBoundingClientRect: () => rect,
    };
  }
  function context(name) {
    return new Proxy({}, {
      get(_, method) {
        if (method === "createLinearGradient") return () => ({ addColorStop() {} });
        return (...args) => draws.push({ name, method, args });
      },
      set() { return true; },
    });
  }
  const backdrop = element({ left: 224, width: width - 224, height: 900 });
  const canvas = element(), spider = element();
  canvas.getContext = () => context("page");
  spider.getContext = () => context("spider");
  const moon = element(), footer = element(), brand = element(), dialog = element();
  const nav = element({ bottom: 250 }), note = element({ top: 700 });
  const sidebar = element({ left: 0, width: 224 });
  sidebar.querySelector = (selector) => selector === "nav" ? nav : note;
  const nodes = {
    ".haunted-backdrop": backdrop, "#page-haunt": canvas,
    "#spider-haunt": spider, "#moon-egg": moon, "#footer-egg": footer,
    ".brand": brand, ".sidebar": sidebar,
    // The hero is outside the viewport; the board and its margins remain visible.
    ".board": element({ left: 262, right: width - 38, top: -400, bottom: 850 }),
  };
  const document = {
    hidden: false, documentElement: { dataset: { atmosphere: "on" } },
    events: {},
    addEventListener(name, callback) { this.events[name] = callback; },
    querySelector(selector) {
      return selector === "dialog[open]" ? (dialogOpen ? dialog : null) : nodes[selector];
    },
    querySelectorAll: () => [dialog],
  };
  const window = { scrollY: 0, events: {} };
  vm.runInNewContext(source, {
    document, window, innerWidth: width, innerHeight: 900, devicePixelRatio: 2,
    performance: { now: () => now },
    requestAnimationFrame(callback) { frames.set(++nextFrame, callback); return nextFrame; },
    cancelAnimationFrame(id) { frames.delete(id); },
    addEventListener(name, callback) { window.events[name] = callback; },
    matchMedia(query) {
      const m = { matches: query.includes("reduced") ? reduced : fine,
        addEventListener(_, callback) { this.change = callback; } };
      media.push(m); return m;
    },
    MutationObserver: class {
      constructor(callback) { this.callback = callback; }
      observe(target) { observers.push({ target, callback: this.callback }); }
    },
  });
  const notify = (target) => observers.filter(o => o.target === target).forEach(o => o.callback());
  return {
    frames, draws, document, backdrop, moon, footer, brand, window,
    step(ms = 50) {
      now += ms;
      const pending = [...frames.values()]; frames.clear();
      pending.forEach(callback => callback(now));
    },
    off() { document.documentElement.dataset.atmosphere = "off"; notify(document.documentElement); },
    modal(open) { dialogOpen = open; notify(dialog); },
    hidden(value) { document.hidden = value; document.events.visibilitychange(); },
    type(text, target = { tagName: "BUTTON" }, extra = {}) {
      for (const key of text) document.events.keydown({ key, target, ...extra });
    },
  };
}

test("footer, moon and BOO reveal visitors with the header offscreen, then sleep", () => {
  for (const trigger of [w => w.footer.events.click(), w => w.moon.events.click(), w => w.type("bOo")]) {
    const w = workspace();
    trigger(w); w.step();
    assert.equal(w.backdrop.dataset.eggs, "awake");
    assert.equal(w.frames.size, 1);
    assert.ok(w.draws.some(d => d.name === "page" && d.method === "fill"));
    assert.ok(w.draws.some(d => d.name === "spider" && d.method === "stroke"));
    w.step(7000);
    assert.equal(w.frames.size, 0);
    assert.equal(w.backdrop.dataset.motion, "idle");
  }
});

test("pointer, scrolling and brand hover wake one bounded loop", () => {
  const w = workspace();
  w.document.events.pointermove({ clientX: 1400, clientY: 400 });
  w.window.scrollY = 200; w.window.events.scroll();
  w.brand.events.pointerenter(); w.step();
  assert.equal(w.frames.size, 1);
  assert.ok(w.draws.some(d => d.name === "page" && d.method === "rotate"));
  assert.ok(w.draws.some(d => d.name === "spider" && d.method === "stroke"));
  w.step(7000);
  assert.equal(w.frames.size, 0);
});

test("Off clears both canvases and blocks every trigger", () => {
  const w = workspace(); w.footer.events.click(); w.step(); w.off();
  assert.equal(w.frames.size, 0);
  assert.equal(w.moon.disabled, true);
  assert.equal(w.footer.disabled, true);
  w.draws.length = 0;
  w.type("boo"); w.footer.events.click();
  w.document.events.pointermove({ clientX: 1400, clientY: 400 });
  w.brand.events.pointerenter();
  assert.equal(w.frames.size, 0);
  assert.equal(w.draws.length, 0);
  assert.equal(w.backdrop.dataset.motion, "off");
});

test("dialogs and hidden tabs pause effects; closing resumes only an active reveal", () => {
  const w = workspace(); w.footer.events.click(); w.step();
  w.modal(true); assert.equal(w.frames.size, 0);
  assert.equal(w.backdrop.dataset.motion, "paused");
  w.modal(false); assert.equal(w.frames.size, 1);
  w.hidden(true); assert.equal(w.frames.size, 0);
  w.step(7000); w.hidden(false);
  assert.equal(w.frames.size, 0);
  assert.equal(w.backdrop.dataset.motion, "idle");
});

test("forms and modifier shortcuts never summon visitors", () => {
  for (const target of [{ tagName: "INPUT" }, { tagName: "TEXTAREA" }, { tagName: "SELECT" }, { tagName: "DIV", isContentEditable: true }]) {
    const w = workspace(); w.type("boo", target);
    assert.equal(w.frames.size, 0);
  }
  for (const modifier of ["ctrlKey", "metaKey", "altKey"]) {
    const w = workspace(); w.type("boo", undefined, { [modifier]: true });
    assert.equal(w.frames.size, 0);
  }
});

test("reduced motion, touch and narrow screens reveal a still composition", () => {
  for (const options of [{ reduced: true }, { fine: false }, { width: 390 }]) {
    const w = workspace(options); w.footer.events.click();
    assert.equal(w.frames.size, 0);
    assert.equal(w.backdrop.dataset.motion, "still");
    assert.equal(w.backdrop.dataset.eggs, "awake");
    assert.ok(w.draws.some(d => d.name === "page" && d.method === "fill"));
  }
});
