/* Page-wide Easter eggs. They occupy margins and navigation whitespace, never data. */
(() => {
  "use strict";
  const backdrop = document.querySelector(".haunted-backdrop");
  const canvas = document.querySelector("#page-haunt");
  const spiderCanvas = document.querySelector("#spider-haunt");
  if (!backdrop || !canvas || !spiderCanvas) return;
  const ctx = canvas.getContext("2d"),
    spider = spiderCanvas.getContext("2d");
  if (!ctx || !spider) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(pointer: fine)");
  let frame = 0,
    last = 0,
    until = 0,
    summonUntil = 0,
    spiderUntil = 0,
    width = 1,
    height = 1,
    left = 0;
  let pointer = { x: innerWidth * 0.85, y: innerHeight * 0.5 },
    light = { ...pointer };
  let scrollY = window.scrollY,
    footprints = [],
    keys = "";
  const enabled = () => document.documentElement.dataset.atmosphere !== "off";
  const blocked = () =>
    document.hidden || Boolean(document.querySelector("dialog[open]"));
  const motion = () => !reduced.matches && fine.matches && innerWidth > 740;
  const clamp = (v, a, b) => Math.max(a, Math.min(v, b));
  function clear() {
    ctx.clearRect(0, 0, width, height);
    spider.clearRect(0, 0, innerWidth, innerHeight);
  }
  function boot(x, y, angle, alpha) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "#4a4d45";
    ctx.filter = "blur(.45px)";
    ctx.beginPath();
    ctx.ellipse(0, -4, 4.2, 7.6, -0.14, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(0.1, 7.5, 3.4, 3.7, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = "destination-out";
    ctx.globalAlpha = alpha * 0.5;
    for (let i = 0; i < 4; i++) {
      ctx.fillRect(-4, -10 + i * 4, 8, 1.1);
    }
    ctx.restore();
  }
  function peeper(x, y, alpha, side) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(side, 1);
    ctx.globalAlpha = alpha;
    ctx.filter = "blur(1.2px)";
    const ink = ctx.createLinearGradient(-9, 0, 13, 0);
    ink.addColorStop(0, "#1e2828");
    ink.addColorStop(0.55, "#657069");
    ink.addColorStop(1, "#111b1a");
    ctx.fillStyle = ink;
    ctx.beginPath();
    ctx.ellipse(0, -19, 8, 13, -0.17, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(-7, -10);
    ctx.bezierCurveTo(-19, -2, -15, 20, -21, 39);
    ctx.lineTo(14, 39);
    ctx.bezierCurveTo(10, 22, 17, -3, 6, -10);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#101819";
    ctx.beginPath();
    ctx.ellipse(2, -18, 4.4, 7.5, -0.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  function drawSpider(now, alpha) {
    spider.clearRect(0, 0, innerWidth, innerHeight);
    if (innerWidth < 951 || now > spiderUntil) return;
    const sidebar = document.querySelector(".sidebar"),
      nav = sidebar?.querySelector("nav"),
      note = sidebar?.querySelector(".sidebar-note");
    if (!sidebar || !nav || !note) return;
    const a = nav.getBoundingClientRect(),
      b = note.getBoundingClientRect(),
      r = sidebar.getBoundingClientRect();
    const top = a.bottom + 17,
      bottom = b.top - 25;
    if (bottom - top < 55) return;
    const x = r.left + r.width * 0.7 + Math.sin(now * 0.001) * 11;
    const progress = clamp((spiderUntil - now) / 5500, 0, 1),
      y = top + (bottom - top) * Math.sin(Math.PI * (1 - progress)) * 0.75;
    spider.save();
    spider.strokeStyle = `rgba(214,201,181,${alpha * 0.42})`;
    spider.lineWidth = 0.6;
    spider.beginPath();
    spider.moveTo(x, top);
    spider.lineTo(x, y);
    spider.stroke();
    spider.translate(x, y);
    spider.globalAlpha = alpha;
    spider.strokeStyle = "#b6a698";
    spider.fillStyle = "#0d1011";
    spider.lineWidth = 1.1;
    for (let side of [-1, 1])
      for (let i = 0; i < 4; i++) {
        const twitch = Math.sin(now * 0.003 + i * 1.7) * 1.5;
        spider.beginPath();
        spider.moveTo(side * 2, i - 3);
        spider.lineTo(side * (9 + (i % 2) * 3), -10 + i * 6 + twitch);
        spider.lineTo(side * (15 + (i % 2) * 3), -3 + i * 6 + twitch);
        spider.stroke();
      }
    spider.beginPath();
    spider.ellipse(0, 2, 4.2, 6, 0, 0, Math.PI * 2);
    spider.fill();
    spider.beginPath();
    spider.ellipse(0, -4, 2.4, 3, 0, 0, Math.PI * 2);
    spider.fill();
    spider.restore();
  }
  function paint(now) {
    clear();
    if (!enabled()) return;
    const summoned = now < summonUntil,
      fade = motion() ? clamp((until - now) / 1100, 0, 1) : 1;
    backdrop.style.setProperty("--watch-x", `${(light.x - left).toFixed(1)}px`);
    backdrop.style.setProperty("--watch-y", `${light.y.toFixed(1)}px`);
    const board = document.querySelector(".board")?.getBoundingClientRect();
    const marginX = board ? board.left - left - 17 : 16;
    for (const print of footprints) {
      const age = (now - print.at) / 3200;
      if (age < 1)
        boot(
          marginX + (print.side ? 5 : -5),
          print.y,
          print.side ? 0.2 : -0.24,
          Math.max(0, 0.21 * (1 - age)) * fade,
        );
    }
    // Opaque panels naturally hide the body; only a narrow figure can peek around their edge.
    if (board && board.top < height && board.bottom > 0) {
      const y = clamp(
        light.y + 25,
        Math.max(45, board.top + 45),
        Math.min(height - 45, board.bottom - 45),
      );
      const near = clamp(1 - Math.abs(pointer.x - board.right) / 160, 0, 1);
      peeper(
        board.right - left + 15,
        y,
        (summoned ? 0.62 : near * 0.42) * fade,
        1,
      );
    }
    if (summoned) {
      for (let i = 0; i < 4; i++)
        boot(
          marginX + (i % 2 ? 5 : -5),
          height * 0.35 + i * 53,
          i % 2 ? 0.2 : -0.24,
          0.18 * fade,
        );
    }
    drawSpider(now, fade);
    backdrop.dataset.eggs = summoned ? "awake" : "hiding";
  }
  function tick(now) {
    frame = 0;
    if (!enabled() || blocked()) {
      sync();
      return;
    }
    if (now - last >= 1000 / 24) {
      last = now;
      light.x += (pointer.x - light.x) * 0.12;
      light.y += (pointer.y - light.y) * 0.12;
      paint(now);
    }
    if (now < until) frame = requestAnimationFrame(tick);
    else {
      clear();
      backdrop.dataset.motion = "idle";
    }
  }
  function wake(duration = 2400) {
    if (!enabled() || blocked()) return;
    until = Math.max(until, performance.now() + duration);
    if (!motion()) {
      light = { ...pointer };
      paint(performance.now());
      backdrop.dataset.motion = "still";
      return;
    }
    backdrop.dataset.motion = "running";
    if (!frame) {
      last = performance.now();
      frame = requestAnimationFrame(tick);
    }
  }
  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    for (const id of ["#moon-egg", "#footer-egg"]) {
      const button = document.querySelector(id);
      if (button) button.disabled = !enabled();
    }
    if (!enabled()) {
      clear();
      footprints = [];
      backdrop.dataset.motion = "off";
      backdrop.dataset.eggs = "hiding";
      return;
    }
    if (blocked()) {
      clear();
      backdrop.dataset.motion = "paused";
      return;
    }
    if (performance.now() < until) wake();
    else {
      clear();
      backdrop.dataset.motion = "idle";
    }
  }
  function summon() {
    if (!enabled() || blocked()) return;
    pointer = { x: innerWidth - 28, y: innerHeight * 0.6 };
    summonUntil = performance.now() + 6000;
    spiderUntil = performance.now() + 5500;
    wake(6200);
  }
  function resize() {
    const r = backdrop.getBoundingClientRect(),
      dpr = Math.min(devicePixelRatio || 1, 1.25);
    left = r.left;
    width = Math.max(1, r.width);
    height = Math.max(1, r.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    spiderCanvas.width = Math.round(innerWidth * dpr);
    spiderCanvas.height = Math.round(innerHeight * dpr);
    spider.setTransform(dpr, 0, 0, dpr, 0, 0);
    sync();
  }
  document.addEventListener(
    "pointermove",
    (event) => {
      if (!motion()) return;
      pointer = { x: event.clientX, y: event.clientY };
      wake();
    },
    { passive: true },
  );
  addEventListener(
    "scroll",
    () => {
      const delta = window.scrollY - scrollY;
      if (Math.abs(delta) > 30) {
        footprints.push({
          y: delta > 0 ? height * 0.76 : height * 0.25,
          side: footprints.length % 2,
          at: performance.now(),
        });
        footprints = footprints.slice(-8);
        scrollY = window.scrollY;
        wake(3300);
      }
    },
    { passive: true },
  );
  for (const id of ["#moon-egg", "#footer-egg"])
    document.querySelector(id)?.addEventListener("click", summon);
  document.querySelector(".brand")?.addEventListener("pointerenter", () => {
    if (motion()) {
      spiderUntil = performance.now() + 5500;
      wake(5600);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      /INPUT|TEXTAREA|SELECT/.test(event.target.tagName) ||
      event.target.isContentEditable ||
      blocked()
    )
      return;
    if (event.key.length === 1) {
      keys = (keys + event.key.toLowerCase()).slice(-3);
      if (keys === "boo") {
        summon();
        keys = "";
      }
    }
  });
  document.addEventListener("visibilitychange", sync);
  reduced.addEventListener("change", sync);
  fine.addEventListener("change", sync);
  new MutationObserver(sync).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-atmosphere"],
  });
  document.querySelectorAll("dialog").forEach((dialog) =>
    new MutationObserver(sync).observe(dialog, {
      attributes: true,
      attributeFilter: ["open"],
    }),
  );
  addEventListener("resize", resize, { passive: true });
  resize();
})();
