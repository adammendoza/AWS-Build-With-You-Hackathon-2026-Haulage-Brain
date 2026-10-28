/* Decorative only. No freight data, network access, or product state lives here. */
(() => {
  "use strict";
  const hero = document.querySelector(".halloween-hero");
  const canvas = document.querySelector("#haunt-fog");
  const toggle = document.querySelector("#atmosphere-toggle");
  const label = document.querySelector("#atmosphere-state");
  const art = document.querySelector(".hero-art");
  if (!hero || !canvas || !toggle || !label) return;
  const ctx = canvas.getContext("2d");
  const preferenceKey = "haulage-brain-atmosphere";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = matchMedia("(pointer: fine)");
  let enabled = true;
  try {
    enabled = localStorage.getItem(preferenceKey) !== "off";
  } catch {
    /* Storage is optional. */
  }
  let frame = 0;
  let lastPaint = 0;
  let elapsed = 0;
  let visible = true;
  let width = 1;
  let height = 1;
  let pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };

  // Low-frequency fractal noise makes soft, irregular wisps instead of particle dots.
  // Build once at 128px, then composite seven sprites at a maximum of 24fps.
  function fogTexture() {
    const tile = document.createElement("canvas");
    tile.width = tile.height = 128;
    const context = tile.getContext("2d");
    if (!context) return null;
    const pixels = context.createImageData(128, 128);
    const grids = [4, 8, 16].map((size) => ({
      size,
      values: Array.from({ length: (size + 1) ** 2 }, () => Math.random()),
    }));
    function sample(grid, u, v) {
      const x = u * grid.size,
        y = v * grid.size;
      const ix = Math.floor(x),
        iy = Math.floor(y);
      const fx = x - ix,
        fy = y - iy;
      const sx = fx * fx * (3 - 2 * fx),
        sy = fy * fy * (3 - 2 * fy);
      const at = (a, b) => grid.values[b * (grid.size + 1) + a];
      return (
        (at(ix, iy) * (1 - sx) + at(ix + 1, iy) * sx) * (1 - sy) +
        (at(ix, iy + 1) * (1 - sx) + at(ix + 1, iy + 1) * sx) * sy
      );
    }
    for (let y = 0; y < 128; y++)
      for (let x = 0; x < 128; x++) {
        const u = x / 128,
          v = y / 128;
        const edge = Math.max(0, 1 - Math.hypot((u - 0.5) * 2, (v - 0.5) * 2));
        const noise =
          sample(grids[0], u, v) * 0.6 +
          sample(grids[1], u, v) * 0.28 +
          sample(grids[2], u, v) * 0.12;
        const i = (y * 128 + x) * 4;
        pixels.data[i] = 132;
        pixels.data[i + 1] = 112;
        pixels.data[i + 2] = 135;
        pixels.data[i + 3] = Math.round(edge ** 1.6 * noise ** 1.5 * 95);
      }
    context.putImageData(pixels, 0, 0);
    return tile;
  }
  const texture = ctx ? fogTexture() : null;
  function canAnimate() {
    return (
      Boolean(ctx && texture) &&
      enabled &&
      !reduced.matches &&
      finePointer.matches &&
      innerWidth > 740
    );
  }
  function occluded() {
    return (
      document.hidden ||
      !visible ||
      Boolean(document.querySelector("dialog[open]"))
    );
  }
  function paint(time) {
    if (!ctx || !texture) return;
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = true;
    for (let i = 0; i < 7; i++) {
      const size = width * (0.54 + (i % 3) * 0.11);
      const phase = time * 0.09 + i * 1.7;
      const x =
        width * (0.08 + (i / 7) * 0.72) +
        Math.sin(phase) * 22 +
        pointer.x * (i % 2 ? -18 : 12);
      const y =
        height * (0.16 + (i % 3) * 0.18) +
        Math.cos(phase * 0.8) * 13 +
        pointer.y * 9;
      ctx.globalAlpha = i % 2 ? 0.55 : 0.4;
      ctx.drawImage(texture, x - size / 2, y - size * 0.25, size, size * 0.56);
    }
    ctx.globalAlpha = 1;
    if (art) {
      art.style.setProperty("--haunt-x", `${(pointer.x * 3.5).toFixed(2)}px`);
      art.style.setProperty("--haunt-y", `${(pointer.y * 2).toFixed(2)}px`);
    }
  }
  function tick(now) {
    frame = 0;
    if (!canAnimate() || occluded()) {
      sync();
      return;
    }
    if (now - lastPaint >= 1000 / 24) {
      // Clamp the time step after a hidden tab resumes; never jump the illustration.
      elapsed += Math.min(now - lastPaint, 70) / 1000;
      lastPaint = now;
      pointer.x += (pointer.targetX - pointer.x) * 0.065;
      pointer.y += (pointer.targetY - pointer.y) * 0.065;
      paint(elapsed);
    }
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    const animate = canAnimate() && !occluded();
    document.documentElement.dataset.atmosphere = enabled ? "on" : "off";
    hero.dataset.motion = !enabled
      ? "off"
      : animate
        ? "running"
        : canAnimate()
          ? "paused"
          : "still";
    toggle.setAttribute("aria-pressed", String(enabled));
    label.textContent = !enabled ? "Off" : canAnimate() ? "On" : "Still";
    toggle.title = enabled
      ? "Turn off decorative atmosphere"
      : "Turn on decorative atmosphere";
    if (
      !enabled ||
      reduced.matches ||
      !finePointer.matches ||
      innerWidth <= 740
    ) {
      pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };
      if (art) {
        art.style.removeProperty("--haunt-x");
        art.style.removeProperty("--haunt-y");
      }
    }
    if (!enabled) ctx?.clearRect(0, 0, width, height);
    else paint(elapsed);
    if (animate && ctx && texture) {
      lastPaint = performance.now();
      frame = requestAnimationFrame(tick);
    }
  }
  function resize() {
    const bounds = canvas.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    sync();
  }
  toggle.addEventListener("click", () => {
    enabled = !enabled;
    try {
      localStorage.setItem(preferenceKey, enabled ? "on" : "off");
    } catch {
      /* Still works for this page. */
    }
    sync();
  });
  hero.addEventListener(
    "pointermove",
    (event) => {
      if (!canAnimate() || occluded()) return;
      const rect = hero.getBoundingClientRect();
      pointer.targetX = Math.max(
        -1,
        Math.min(1, ((event.clientX - rect.left) / rect.width - 0.5) * 2),
      );
      pointer.targetY = Math.max(
        -1,
        Math.min(1, ((event.clientY - rect.top) / rect.height - 0.5) * 2),
      );
    },
    { passive: true },
  );
  hero.addEventListener(
    "pointerleave",
    () => {
      pointer.targetX = pointer.targetY = 0;
    },
    { passive: true },
  );
  document.addEventListener("visibilitychange", sync);
  reduced.addEventListener("change", sync);
  finePointer.addEventListener("change", sync);
  if (typeof IntersectionObserver === "function") {
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    }).observe(hero);
  }
  document.querySelectorAll("dialog").forEach((dialog) => {
    new MutationObserver(sync).observe(dialog, {
      attributes: true,
      attributeFilter: ["open"],
    });
  });
  if (typeof ResizeObserver === "function")
    new ResizeObserver(resize).observe(hero);
  else addEventListener("resize", resize, { passive: true });
  resize();
})();
