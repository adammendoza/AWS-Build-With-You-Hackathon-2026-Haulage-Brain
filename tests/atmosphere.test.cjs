// Run with: node --test tests/atmosphere.test.cjs
// These test attention and accessibility contracts, without a browser or provider calls.
const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(
  path.join(__dirname, "../src/load_quoting_swarm/web_assets/atmosphere.js"),
  "utf8",
);

function workspace({
  reduced = false,
  width = 1440,
  fine = true,
  saved = "on",
  canvasAvailable = true,
  storageAvailable = true,
} = {}) {
  const frames = new Map(),
    media = [],
    dialogs = [],
    intersections = [];
  let frameId = 0,
    now = 0,
    dialogOpen = false;
  const element = () => ({
    dataset: {},
    events: {},
    addEventListener(name, fn) {
      this.events[name] = fn;
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  });
  const hero = element(),
    canvas = element(),
    toggle = element(),
    label = element(),
    sweep = element(),
    action = element(),
    whisper = element();
  const gradient = () => ({ addColorStop() {} });
  const context = {
    clearRect() {},
    setTransform() {},
    drawImage() {},
    putImageData() {},
    fillRect() {},
    save() {},
    restore() {},
    translate() {},
    beginPath() {},
    moveTo() {},
    bezierCurveTo() {},
    lineTo() {},
    closePath() {},
    fill() {},
    ellipse() {},
    createRadialGradient: gradient,
    createLinearGradient: gradient,
    createImageData(w, h) {
      return { data: new Uint8ClampedArray(w * h * 4) };
    },
  };
  canvas.getContext = () => (canvasAvailable ? context : null);
  canvas.getBoundingClientRect = () => ({
    left: 300,
    right: 1000,
    top: 100,
    bottom: 360,
    width: 700,
    height: 260,
  });
  const nodes = {
    ".halloween-hero": hero,
    "#haunt-fog": canvas,
    "#atmosphere-toggle": toggle,
    "#atmosphere-state": label,
    "#scene-sweep": sweep,
    "#scene-action-label": action,
    "#scene-whisper": whisper,
  };
  const document = {
    hidden: false,
    documentElement: { dataset: {} },
    events: {},
    addEventListener(name, fn) {
      this.events[name] = fn;
    },
    querySelector(selector) {
      return selector === "dialog[open]"
        ? dialogOpen
          ? {}
          : null
        : nodes[selector];
    },
    querySelectorAll() {
      return [{}];
    },
    createElement() {
      return { getContext: () => context };
    },
  };
  const storage = {
    value: saved,
    getItem() {
      if (!storageAvailable) throw Error("blocked");
      return this.value;
    },
    setItem(key, value) {
      if (!storageAvailable) throw Error("blocked");
      this.value = value;
    },
  };
  const sandbox = {
    document,
    localStorage: storage,
    innerWidth: width,
    devicePixelRatio: 2,
    performance: { now: () => now },
    matchMedia(query) {
      const item = {
        matches: query.includes("reduced-motion") ? reduced : fine,
        addEventListener(name, fn) {
          this.changed = fn;
        },
      };
      media.push(item);
      return item;
    },
    requestAnimationFrame(fn) {
      frames.set(++frameId, fn);
      return frameId;
    },
    cancelAnimationFrame(id) {
      frames.delete(id);
    },
    IntersectionObserver: class {
      constructor(fn) {
        intersections.push(fn);
      }
      observe() {}
    },
    MutationObserver: class {
      constructor(fn) {
        dialogs.push(fn);
      }
      observe() {}
    },
    ResizeObserver: class {
      observe() {}
    },
    addEventListener() {},
  };
  vm.runInNewContext(source, sandbox);
  return {
    hero,
    toggle,
    sweep,
    action,
    frames,
    media,
    document,
    storage,
    showDialog(value) {
      dialogOpen = value;
      dialogs[0]();
    },
    showHero(value) {
      intersections[0]([{ isIntersecting: value }]);
    },
    advance(ms) {
      for (let t = 0; t < ms; t += 50) {
        now += 50;
        const pending = [...frames.entries()];
        for (const [id, fn] of pending) {
          frames.delete(id);
          fn(now);
        }
        assert.ok(frames.size <= 1, "only one renderer loop may be owned");
      }
    },
  };
}

test("animation pauses for dialogs, hidden tabs, and off-screen content, then resumes once", () => {
  const app = workspace();
  assert.equal(app.frames.size, 1);
  app.showDialog(true);
  assert.equal(app.hero.dataset.motion, "paused");
  assert.equal(app.frames.size, 0);
  app.showDialog(false);
  assert.equal(app.frames.size, 1);
  app.showHero(false);
  assert.equal(app.frames.size, 0);
  app.showHero(true);
  assert.equal(app.frames.size, 1);
  app.document.hidden = true;
  app.document.events.visibilitychange();
  assert.equal(app.frames.size, 0);
  app.document.hidden = false;
  app.document.events.visibilitychange();
  assert.equal(app.frames.size, 1);
  app.advance(1000);
});

test("reduced motion, touch, and mobile use an instant reveal without starting an animation", () => {
  for (const options of [
    { reduced: true },
    { fine: false },
    { width: 390 },
    { width: 320 },
  ]) {
    const app = workspace(options);
    assert.equal(app.hero.dataset.motion, "still");
    assert.equal(app.frames.size, 0);
    app.sweep.events.click();
    assert.equal(app.hero.dataset.presence, "revealed");
    assert.equal(app.frames.size, 0);
    app.sweep.events.click();
    assert.equal(app.hero.dataset.presence, "hidden");
  }
});

test("the explicit torch sweep finds the silhouette and remains separate from decisions", () => {
  const app = workspace();
  assert.equal(app.hero.dataset.presence, "hidden");
  app.sweep.events.click();
  app.advance(3500);
  assert.equal(app.action.textContent, "Look again");
  assert.equal(app.hero.dataset.presence, "revealed");
});

test("turning effects off stops the renderer, persists the preference, and disables the sweep", () => {
  const app = workspace();
  app.toggle.events.click();
  assert.equal(app.frames.size, 0);
  assert.equal(app.storage.value, "off");
  assert.equal(app.sweep.disabled, true);
  const restored = workspace({ saved: "off" });
  assert.equal(restored.frames.size, 0);
  assert.equal(restored.toggle["aria-pressed"], "false");
});

test("preference changes and unavailable browser capabilities degrade gracefully", () => {
  const app = workspace();
  app.media[0].matches = true;
  app.media[0].changed();
  assert.equal(app.hero.dataset.motion, "still");
  assert.equal(app.frames.size, 0);
  const noCanvas = workspace({ canvasAvailable: false });
  assert.equal(noCanvas.frames.size, 0);
  assert.equal(noCanvas.sweep.disabled, true);
  const noStorage = workspace({ storageAvailable: false });
  noStorage.toggle.events.click();
  assert.equal(noStorage.hero.dataset.motion, "off");
});
