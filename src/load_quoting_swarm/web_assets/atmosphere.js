/* A hand-built photographic ghost story. Entirely separate from load/decision state. */
(() => {
  "use strict";
  const hero = document.querySelector(".halloween-hero");
  const canvas = document.querySelector("#haunt-fog");
  const toggle = document.querySelector("#atmosphere-toggle");
  const label = document.querySelector("#atmosphere-state");
  const sweep = document.querySelector("#scene-sweep");
  const action = document.querySelector("#scene-action-label");
  const whisper = document.querySelector("#scene-whisper");
  const hint = document.querySelector("#scene-help");
  if (!hero || !canvas || !toggle || !sweep) return;
  const ctx = canvas.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(pointer: fine)");
  const key = "haulage-brain-atmosphere";
  let enabled = true;
  try {
    enabled = localStorage.getItem(key) !== "off";
  } catch {
    /* Optional persistence. */
  }
  let width = 1,
    height = 1,
    frame = 0,
    last = 0,
    elapsed = 0,
    visible = true;
  let pointer = { x: 0.65, y: 0.52, targetX: 0.65, targetY: 0.52 };
  let sweeping = 0,
    revealed = false,
    hover = false;
  const wake = [];
  const smooth = (a, b, t) => a + (b - a) * t;
  function texture() {
    const tile = document.createElement("canvas");
    tile.width = tile.height = 192;
    const c = tile.getContext("2d");
    if (!c) return null;
    const pixels = c.createImageData(192, 192);
    const grids = [4, 9, 19].map((n) => ({
      n,
      v: Array.from({ length: (n + 1) ** 2 }, () => Math.random()),
    }));
    const noise = (g, u, v) => {
      const x = u * g.n,
        y = v * g.n,
        ix = Math.floor(x),
        iy = Math.floor(y),
        fx = x - ix,
        fy = y - iy,
        sx = fx * fx * (3 - 2 * fx),
        sy = fy * fy * (3 - 2 * fy),
        at = (a, b) => g.v[b * (g.n + 1) + a];
      return (
        (at(ix, iy) * (1 - sx) + at(ix + 1, iy) * sx) * (1 - sy) +
        (at(ix, iy + 1) * (1 - sx) + at(ix + 1, iy + 1) * sx) * sy
      );
    };
    for (let y = 0; y < 192; y++)
      for (let x = 0; x < 192; x++) {
        const u = x / 192,
          v = y / 192,
          edge = Math.max(0, 1 - Math.hypot((u - 0.5) * 2, (v - 0.5) * 2)),
          n =
            noise(grids[0], u, v) * 0.58 +
            noise(grids[1], u, v) * 0.3 +
            noise(grids[2], u, v) * 0.12,
          i = (y * 192 + x) * 4;
        pixels.data[i] = 215;
        pixels.data[i + 1] = 220;
        pixels.data[i + 2] = 211;
        pixels.data[i + 3] = Math.round(edge ** 1.25 * n ** 1.2 * 200);
      }
    c.putImageData(pixels, 0, 0);
    return tile;
  }
  const fog = ctx ? texture() : null;
  function animated() {
    return (
      Boolean(ctx && fog) &&
      enabled &&
      !reduced.matches &&
      fine.matches &&
      innerWidth > 740
    );
  }
  function blocked() {
    return (
      document.hidden ||
      !visible ||
      Boolean(document.querySelector("dialog[open]"))
    );
  }
  function apparition(strength) {
    if (strength < 0.025) return;
    const x = width * 0.515,
      y = height * 0.87,
      h = height * 0.25;
    ctx.save();
    ctx.translate(x, y);
    ctx.globalAlpha = strength;
    ctx.filter = "blur(1.1px)";
    const cloth = ctx.createLinearGradient(-h * 0.15, 0, h * 0.18, 0);
    cloth.addColorStop(0, "#121a19");
    cloth.addColorStop(0.48, "#4d5750");
    cloth.addColorStop(1, "#18201e");
    ctx.fillStyle = cloth;
    // An indistinct person at the vanishing point, with irregular cloth edges; no cartoon eyes.
    ctx.beginPath();
    ctx.moveTo(-h * 0.1, -h * 0.72);
    ctx.bezierCurveTo(-h * 0.27, -h * 0.62, -h * 0.19, -h * 0.27, -h * 0.25, 0);
    ctx.lineTo(-h * 0.09, -h * 0.02);
    ctx.lineTo(-h * 0.025, 0);
    ctx.lineTo(h * 0.05, -h * 0.04);
    ctx.lineTo(h * 0.22, 0);
    ctx.bezierCurveTo(
      h * 0.16,
      -h * 0.23,
      h * 0.24,
      -h * 0.65,
      h * 0.09,
      -h * 0.72,
    );
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(0, -h * 0.8, h * 0.115, h * 0.17, -0.06, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#0c1111";
    ctx.beginPath();
    ctx.ellipse(h * 0.012, -h * 0.78, h * 0.066, h * 0.1, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = strength * 0.18;
    ctx.fillStyle = "#101515";
    ctx.beginPath();
    ctx.ellipse(0, h * 0.08, h * 0.32, h * 0.08, 0.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  function paint() {
    if (!ctx || !fog) return;
    ctx.clearRect(0, 0, width, height);
    if (!enabled) return;
    ctx.fillStyle = "rgba(7,16,14,.32)";
    ctx.fillRect(0, 0, width, height);
    // Two depths of broad, irregular mist. The front layer drifts against the far layer.
    for (let i = 0; i < 11; i++) {
      const size = width * (0.6 + (i % 3) * 0.16),
        phase = elapsed * (i % 2 ? 0.055 : -0.035) + i * 2.1,
        x = width * ((i % 5) / 4) + Math.sin(phase) * width * 0.11,
        y = height * (0.32 + (i % 4) * 0.18) + Math.cos(phase * 0.7) * 12;
      ctx.globalAlpha = (i < 5 ? 0.45 : 0.3) * (animated() ? 1 : .55);
      ctx.drawImage(fog, x - size * 0.5, y - size * 0.18, size, size * 0.45);
    }
    ctx.globalAlpha = 1;
    const bx = pointer.x * width,
      by = pointer.y * height,
      r = width * 0.22;
    // Remove the veil inside a soft optical beam, revealing the underlying photograph.
    if (hover || sweeping || revealed) {
      ctx.globalCompositeOperation = "destination-out";
      const hole = ctx.createRadialGradient(bx, by, r * 0.08, bx, by, r);
      hole.addColorStop(0, "rgba(0,0,0,.95)");
      hole.addColorStop(0.52, "rgba(0,0,0,.65)");
      hole.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = hole;
      ctx.fillRect(0, 0, width, height);
      for (const trail of wake) {
        const strength = Math.max(0, 1 - (elapsed - trail.at) / 0.8) * 0.3;
        if (!strength) continue;
        const x = trail.x * width,
          y = trail.y * height,
          radius = r * 0.55;
        const cleared = ctx.createRadialGradient(x, y, 0, x, y, radius);
        cleared.addColorStop(0, `rgba(0,0,0,${strength})`);
        cleared.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = cleared;
        ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
      }
      ctx.globalCompositeOperation = "source-over";
      ctx.save();
      ctx.filter = "blur(9px)";
      const shaft = ctx.createLinearGradient(width * 0.8, height * 1.3, bx, by);
      shaft.addColorStop(0, "rgba(255,232,185,0)");
      shaft.addColorStop(0.65, "rgba(255,237,190,.035)");
      shaft.addColorStop(1, "rgba(255,243,204,.13)");
      ctx.fillStyle = shaft;
      ctx.beginPath();
      ctx.moveTo(width * 0.8, height * 1.3);
      ctx.lineTo(bx - r * 0.55, by);
      ctx.lineTo(bx + r * 0.55, by);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      const beam = ctx.createRadialGradient(bx, by, 0, bx, by, r);
      beam.addColorStop(0, "rgba(255,229,176,.13)");
      beam.addColorStop(0.6, "rgba(235,231,192,.04)");
      beam.addColorStop(1, "rgba(235,231,192,0)");
      ctx.fillStyle = beam;
      ctx.fillRect(0, 0, width, height);
    }
    const distance = Math.hypot((pointer.x - 0.515) * 1.3, pointer.y - 0.74);
    const presence =
      hover || sweeping || revealed ? Math.max(0, 1 - distance / 0.24) : 0.035;
    apparition(presence * 0.85);
    const close = presence > 0.55;
    if (hero.dataset.presence === (close ? "revealed" : "hidden")) return;
    whisper.textContent = close
      ? "YOU WEREN’T ALONE."
      : "SOMETHING IS OUT THERE.";
    hero.dataset.presence = close ? "revealed" : "hidden";
  }
  function tick(now) {
    frame = 0;
    if (!animated() || blocked()) {
      sync();
      return;
    }
    if (now - last >= 1000 / 24) {
      const dt = Math.min((now - last) / 1000, 0.07);
      elapsed += dt;
      last = now;
      if (sweeping > 0) {
        sweeping = Math.max(0, sweeping - dt);
        const p = 1 - sweeping / 3;
        pointer.targetX =
          p < 0.65 ? 0.12 + p * 0.95 : smooth(0.7375, 0.515, (p - 0.65) / 0.35);
        pointer.targetY = smooth(0.58, 0.74, p);
        if (!sweeping) {
          revealed = true;
          action.textContent = "Look again";
        }
      }
      pointer.x = smooth(pointer.x, pointer.targetX, 0.12);
      pointer.y = smooth(pointer.y, pointer.targetY, 0.12);
      if (hover || sweeping) {
        wake.unshift({ x: pointer.x, y: pointer.y, at: elapsed });
        if (wake.length > 14) wake.pop();
      }
      paint();
    }
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    const run = animated() && !blocked();
    document.documentElement.dataset.atmosphere = enabled ? "on" : "off";
    hero.dataset.motion = !enabled
      ? "off"
      : run
        ? "running"
        : animated()
          ? "paused"
          : "still";
    toggle.setAttribute("aria-pressed", String(enabled));
    label.textContent = !enabled ? "Off" : animated() ? "On" : "Still";
    if (hint) hint.textContent = animated() ? "or move your light across the trees" : "tap to look into the mist";
    sweep.disabled = !enabled || !ctx || !fog;
    toggle.title = enabled
      ? "Turn off the interactive atmosphere"
      : "Turn on the interactive atmosphere";
    if (!enabled) {
      sweeping = 0;
      revealed = false;
      hover = false;
      action.textContent = "Sweep the fog";
      wake.length = 0;
      hero.dataset.presence = "hidden";
      whisper.textContent = "SOMETHING IS OUT THERE.";
    }
    paint();
    if (run) {
      last = performance.now();
      frame = requestAnimationFrame(tick);
    }
  }
  function resize() {
    const r = canvas.getBoundingClientRect(),
      dpr = Math.min(devicePixelRatio || 1, 1.5);
    width = Math.max(1, r.width);
    height = Math.max(1, r.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    sync();
  }
  toggle.addEventListener("click", () => {
    enabled = !enabled;
    try {
      localStorage.setItem(key, enabled ? "on" : "off");
    } catch {}
    sync();
  });
  sweep.addEventListener("click", () => {
    if (!enabled || !ctx) return;
    hover = false;
    if (animated()) {
      sweeping = 3;
      revealed = false;
      action.textContent = "Follow the light…";
    } else {
      revealed = !revealed;
      pointer.x = pointer.targetX = 0.515;
      pointer.y = pointer.targetY = 0.74;
      action.textContent = revealed ? "Look again" : "Sweep the fog";
      paint();
    }
    sync();
  });
  hero.addEventListener(
    "pointermove",
    (event) => {
      if (!animated() || blocked() || sweeping) return;
      const rect = canvas.getBoundingClientRect();
      hover =
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom;
      pointer.targetX = Math.max(
        0.05,
        Math.min(0.95, (event.clientX - rect.left) / rect.width),
      );
      pointer.targetY = Math.max(
        0.05,
        Math.min(0.95, (event.clientY - rect.top) / rect.height),
      );
    },
    { passive: true },
  );
  hero.addEventListener(
    "pointerleave",
    () => {
      hover = false;
      if (!sweeping && !revealed) {
        pointer.targetX = 0.65;
        pointer.targetY = 0.52;
      }
    },
    { passive: true },
  );
  document.addEventListener("visibilitychange", sync);
  reduced.addEventListener("change", sync);
  fine.addEventListener("change", sync);
  if (typeof IntersectionObserver === "function")
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    }).observe(hero);
  document.querySelectorAll("dialog").forEach((dialog) =>
    new MutationObserver(sync).observe(dialog, {
      attributes: true,
      attributeFilter: ["open"],
    }),
  );
  if (typeof ResizeObserver === "function")
    new ResizeObserver(resize).observe(hero);
  else addEventListener("resize", resize, { passive: true });
  resize();
})();
