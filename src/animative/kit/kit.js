/* Heimdall graphics kit: builds one shot from the JSON spec embedded in the page.
 *
 * Everything is a pure function of the spec. Randomness comes from a seeded PRNG,
 * times come from the spec, and the one GSAP timeline is registered paused, so
 * HyperFrames can seek any frame and get the same picture.
 */
(function () {
  "use strict";
  const W = 960, H = 540;
  const spec = JSON.parse(document.getElementById("shot-spec").textContent);
  const root = document.getElementById("root");
  const FRAME = spec.fps_den / spec.fps_num;
  const DUR = spec.dur;
  const tl = gsap.timeline({ paused: true });
  /* A child placed before 0 makes GSAP shift every other child later. Clamp at the door. */
  ["to", "from", "fromTo", "set"].forEach((m) => {
    const f = tl[m].bind(tl);
    tl[m] = function () {
      const a = [...arguments];
      const i = m === "fromTo" ? 3 : 2;
      if (typeof a[i] === "number" && a[i] < 0) a[i] = 0;
      return f(...a);
    };
  });

  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hash(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
  const R = rng(hash(spec.id));
  const rr = (a, b) => a + (b - a) * R();

  function el(tag, cls, parent, attrs) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (attrs) for (const k in attrs) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "html") n.innerHTML = attrs[k];
      else if (k === "style") Object.assign(n.style, attrs[k]);
      else n.setAttribute(k, attrs[k]);
    }
    (parent || root).appendChild(n);
    return n;
  }
  const NS = "http://www.w3.org/2000/svg";
  function sv(tag, parent, attrs) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs || {}) {
      if (k === "text") n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]);
    }
    parent.appendChild(n);
    return n;
  }
  function svgLayer(parent, vb) {
    const wrap = el("div", "svgwrap", parent);
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", vb || "0 0 960 540");
    s.setAttribute("preserveAspectRatio", "xMidYMid slice");
    wrap.appendChild(s);
    return { wrap, svg: s };
  }
  const clamp = (t) => Math.max(0, Math.min(DUR - FRAME, t));

  /* ---------- camera moves ---------- */
  function move(node, kind, t0, t1, opts) {
    opts = opts || {};
    const d = Math.max(0.2, t1 - t0);
    const rot0 = opts.dutch ? rr(-5, -3) : 0;
    const rot1 = opts.dutch ? rot0 + rr(-2, 2.5) : 0;
    const ease = "sine.inOut";
    const sgn = R() < 0.5 ? -1 : 1;
    switch (kind) {
      case "dolly_in": case "zoom_in":
        tl.fromTo(node, { scale: 1.06, x: 0, y: 0, rotation: rot0 }, { scale: kind === "zoom_in" ? 1.32 : 1.22, x: sgn * 10, y: -6, rotation: rot1, duration: d, ease: "power1.inOut" }, t0); break;
      case "zoom_out":
        tl.fromTo(node, { scale: 1.36, x: sgn * 14, y: 8, rotation: rot0 }, { scale: 1.06, x: 0, y: 0, rotation: rot1, duration: d, ease: "power2.out" }, t0); break;
      case "pan":
        tl.fromTo(node, { scale: 1.2, x: -60 * sgn, rotation: rot0 }, { scale: 1.24, x: 60 * sgn, rotation: rot1, duration: d, ease }, t0); break;
      case "truck":
        tl.fromTo(node, { scale: 1.18, x: 50 * sgn, y: 10, rotation: rot0 }, { scale: 1.18, x: -50 * sgn, y: -10, rotation: rot1, duration: d, ease }, t0); break;
      case "handheld": {
        tl.fromTo(node, { scale: 1.16, rotation: rot0 }, { scale: 1.24, rotation: rot1, duration: d, ease: "none" }, t0);
        const n = Math.max(3, Math.round(d / 0.28));
        for (let i = 0; i < n; i++) tl.to(node, { x: rr(-14, 14), y: rr(-10, 10), duration: d / n, ease: "sine.inOut" }, t0 + (i * d) / n);
        break;
      }
      default: /* drift: nothing ever sits still */
        tl.fromTo(node, { scale: 1.08, x: -12 * sgn, rotation: rot0 }, { scale: 1.16, x: 12 * sgn, rotation: rot1, duration: d, ease }, t0);
    }
  }

  /* ---------- layers ---------- */
  const shakeL = el("div", "shake", root);
  const camL = el("div", "cam", shakeL);
  const bgL = el("div", "layer", camL);
  const gfxRoot = el("div", "layer", shakeL);
  let gfxL = gfxRoot; /* each graphic gets its own layer, hidden until its start */
  const presL = el("div", "layer", shakeL);
  const fxL = el("div", "layer", root);
  const hudL = el("div", "layer", root);

  /* ---------- background segments ---------- */
  function background() {
    const segs = spec.bg || [];
    if (!segs.length) {
      const kind = spec.backdrop || "grid";
      const b = el("div", "fill " + (kind === "burst" ? "bg-burst" : "bg-grid"), bgL);
      if (kind === "burst") {
        const r = el("div", "rays", b);
        tl.fromTo(r, { rotation: 0 }, { rotation: 40, duration: DUR, ease: "none" }, 0);
      }
      move(camL, spec.move || "drift", 0, DUR, {});
      return;
    }
    segs.forEach((s, i) => {
      const seg = el("div", "layer " + (s.grade ? "grade-" + s.grade : ""), bgL);
      const cam = el("div", "cam", seg);
      /* a crop is a fixed second framing of the same picture; the camera move runs on top of it */
      const frame = s.crop ? el("div", "layer", cam, { style: { transform: "scale(" + s.crop[0] + ")", transformOrigin: s.crop[1] + "% " + s.crop[2] + "%" } }) : cam;
      const start = s.t0 || 0, end = s.t1 == null ? DUR : s.t1;
      if (s.fit === "contain") {
        const blur = el("img", "media media-blur", frame, { src: s.src, alt: "" });
        blur.id = "bgb-" + i;
      }
      if (s.kind === "video") {
        el("video", "media" + (s.fit === "contain" ? " media-fit" : ""), frame, {
          id: "bgv-" + i, src: s.src, muted: "", playsinline: "",
          "data-start": String(start), "data-duration": String(end - start), "data-media-start": String(s.media_start || 0),
          "data-track-index": String(i),
        });
      } else {
        el("img", "media" + (s.fit === "contain" ? " media-fit" : ""), frame, { src: s.src, alt: "", id: "bgi-" + i });
      }
      if (s.grade === "red") el("div", "fill tint-red", seg);
      if (i > 0 || start > 0) tl.set(seg, { opacity: 0 }, 0).set(seg, { opacity: 1 }, start);
      if (end < DUR) tl.set(seg, { opacity: 0 }, end);
      move(cam, s.move || spec.move || "drift", start, end, { dutch: s.dutch || spec.angle === "dutch" });
    });
    if (spec.grade === "red") el("div", "fill tint-red", camL);
  }

  /* ---------- components ---------- */
  const C = {};

  C["kinetic-caption"] = function (d, t0, t1) {
    const k = el("div", "kin" + (d.top ? " top" : ""), gfxL);
    const tx = el("div", "kin-text", k);
    const letters = [...d.text].map((ch) => el("span", "", tx, { text: ch === " " ? " " : ch }));
    tl.fromTo(tx, { scale: 2.6, rotation: -6, opacity: 0 }, { scale: 1, rotation: -3, opacity: 1, duration: 0.22, ease: "back.out(2.2)" }, t0);
    letters.forEach((l, i) => tl.fromTo(l, { y: -40 }, { y: 0, duration: 0.18, ease: "power3.out" }, t0 + i * 0.02));
    tl.to(tx, { scale: 1.08, duration: t1 - t0 - 0.4, ease: "sine.inOut" }, t0 + 0.25);
    tl.to(tx, { scale: 0.2, opacity: 0, duration: 0.14, ease: "power2.in" }, t1 - 0.15);
  };

  C["name-card"] = function (d, t0, t1) {
    const side = spec.card_side === "right" ? " right" : "";
    const c = el("div", "card" + side, gfxL);
    el("div", "card-bar", c);
    const b = el("div", "card-body", c);
    el("div", "card-name", b, { text: d.name });
    const rows = [["from", d.country], ["maker", d.maker], ["role", d.role]];
    rows.forEach(([k, v]) => { const r = el("div", "card-row", b); el("b", "", r, { text: k }); r.appendChild(document.createTextNode(v)); });
    const y = el("div", "card-year", c);
    y.appendChild(document.createTextNode(d.year));
    el("small", "", y, { text: d.year_means });
    const dx = side ? 380 : -380;
    tl.fromTo(c, { x: dx, skewX: -12 }, { x: 0, skewX: 0, duration: 0.32, ease: "back.out(1.6)" }, t0);
    tl.fromTo(y, { scale: 0, rotation: -20 }, { scale: 1, rotation: 4, duration: 0.25, ease: "back.out(3)" }, t0 + 0.2);
    tl.to(c, { x: dx * 0.04, duration: Math.max(0.1, t1 - t0 - 0.6), ease: "sine.inOut" }, t0 + 0.32);
    tl.to(c, { x: dx, opacity: 0, duration: 0.2, ease: "power2.in" }, t1 - 0.22);
  };

  C["title-card"] = function (d, t0, t1) {
    const box = el("div", "layer", gfxL);
    const rot = el("div", "rotor", box);
    tl.fromTo(rot, { rotation: 0, scale: 0.4, opacity: 0.9 }, { rotation: 1440, scale: 1.8, opacity: 0, duration: 1.0, ease: "power2.in" }, t0);
    const words = d.title.split(" ");
    const html = words.map((w, i) => (i === words.length - 1 ? '<span class="acc">' + w + "</span>" : w)).join(" ");
    const g1 = el("div", "glitch r", box); el("div", "title-word", g1, { html });
    const g2 = el("div", "glitch b", box); el("div", "title-word", g2, { html });
    const t = el("div", "title", box); const word = el("div", "title-word", t, { html });
    tl.fromTo(word, { scale: 3, opacity: 0, filter: "blur(12px)" }, { scale: 1, opacity: 1, filter: "blur(0px)", duration: 0.45, ease: "expo.out" }, t0 + 0.35);
    tl.to(word, { scale: 1.12, duration: t1 - t0 - 0.9, ease: "sine.inOut" }, t0 + 0.8);
    const r2 = rng(hash(spec.id + "glitch"));
    for (let i = 0; i < 9; i++) {
      const at = t0 + 0.6 + r2() * (t1 - t0 - 0.9);
      [g1, g2].forEach((g, j) => {
        tl.set(g, { opacity: 0.85, x: (j ? 1 : -1) * (6 + r2() * 14), clipPath: "inset(" + Math.round(r2() * 60) + "% 0 " + Math.round(r2() * 30) + "% 0)" }, at);
        tl.set(g, { opacity: 0, x: 0 }, at + 2 * FRAME);
      });
      tl.set(word, { x: (r2() - 0.5) * 16 }, at).set(word, { x: 0 }, at + 2 * FRAME);
    }
    tl.to(box, { scale: 1.6, opacity: 0, duration: 0.2, ease: "power2.in" }, t1 - 0.2);
  };

  function tickerDom(parent, cls, year) {
    const t = el("div", cls, parent);
    const box = el("div", "ticker-box", t);
    const strips = [];
    String(year).split("").forEach(() => {
      const col = el("div", "ticker-col", box);
      const st = el("div", "ticker-strip", col);
      for (let r = 0; r < 3; r++) for (let n = 0; n < 10; n++) el("span", "", st, { text: String(n) });
      strips.push(st);
    });
    return { t, strips };
  }
  function rollTicker(strips, from, to, at, dur, cell) {
    const a = String(from).padStart(4, "0"), b = String(to).padStart(4, "0");
    strips.forEach((st, i) => {
      const da = +a[i], db = +b[i];
      const spin = (i >= 2 && a !== b) ? 10 : 0;
      tl.fromTo(st, { y: -(10 + da) * cell }, { y: -(10 + db + (db < da ? 10 : 0) + (spin && db >= da ? 0 : 0)) * cell, duration: dur, ease: "power3.out" }, at + i * 0.04);
    });
  }

  C["year-ticker"] = function (d, t0, t1) {
    const { t, strips } = tickerDom(gfxL, "big-ticker", d.year);
    rollTicker(strips, d.from || 2025, d.year, t0 + 0.05, Math.min(1.0, t1 - t0 - 0.3), 150);
    tl.fromTo(t, { scale: 0.6 }, { scale: 1.05, duration: t1 - t0, ease: "power1.out" }, t0);
    if (d.map && WORLD_PLACES[d.map]) {
      const p = WORLD_PLACES[d.map];
      const { svg } = svgLayer(bgL, "0 0 2000 1000");
      drawWorld(svg, []);
      const [x, y] = proj(p);
      ping(svg, x, y, t0 + 0.6, 4, 60, 3);
    }
  };

  C["stamp"] = function (d, t0, t1) {
    const s = el("div", "stamp", gfxL);
    const b = el("div", "stamp-box", s, { text: d.text });
    tl.fromTo(b, { scale: 4, rotation: -30, opacity: 0 }, { scale: 1, rotation: -9, opacity: 1, duration: 0.18, ease: "power4.in" }, t0 + 0.1);
    tl.to(b, { scale: 1.06, duration: t1 - t0 - 0.5, ease: "sine.inOut" }, t0 + 0.3);
  };

  C["spec-card"] = function (d, t0, t1) {
    const s = el("div", "spec", gfxL);
    const a = el("div", "spec-item", s);
    const an = el("div", "spec-num", a); const av = el("span", "", an, { text: "0" }); el("small", "", an, { text: "m" });
    el("div", "spec-lbl", a, { text: "wingspan" }); const ab = el("i", "", el("div", "spec-bar", a));
    const b = el("div", "spec-item", s);
    const bn = el("div", "spec-num", b); const bv = el("span", "", bn, { text: "0" }); el("small", "", bn, { text: "h+" });
    el("div", "spec-lbl", b, { text: "in the air" }); const bb = el("i", "", el("div", "spec-bar", b));
    const steps = 14;
    for (let i = 0; i <= steps; i++) {
      tl.set(av, { textContent: String(Math.round((d.wingspan_m * i) / steps)) }, t0 + 0.2 + i * 0.05);
      tl.set(bv, { textContent: String(Math.round((parseInt(d.endurance) * i) / steps)) }, t0 + 0.5 + i * 0.05);
    }
    tl.fromTo(ab, { scaleX: 0 }, { scaleX: 0.8, duration: 0.7, ease: "power2.out" }, t0 + 0.2);
    tl.fromTo(bb, { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: "power2.out" }, t0 + 0.5);
    tl.fromTo([a, b], { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, stagger: 0.25, ease: "back.out(2)" }, t0);
  };

  C["counter"] = function (d, t0, t1) {
    const c = el("div", "counter", gfxL);
    if (d.flag === "UA") el("div", "flag-ua", c);
    const n = el("div", "counter-num", c, { text: "0" });
    el("div", "counter-unit", c, { text: d.unit });
    const target = parseInt(String(d.to).replace(/[^0-9]/g, ""), 10);
    const dur = Math.min(1.6, (t1 - t0) * 0.6);
    const steps = Math.round(dur / FRAME);
    for (let i = 0; i <= steps; i++) {
      const p = 1 - Math.pow(1 - i / steps, 3);
      tl.set(n, { textContent: Math.round(target * p).toLocaleString("en-US") }, t0 + 0.1 + i * FRAME);
    }
    tl.set(n, { textContent: d.to }, t0 + 0.1 + dur + FRAME);
    tl.set(n, { scale: 1.6 }, t0 + 0.1 + dur).to(n, { scale: 1, duration: 0.25, ease: "back.out(3)" }, t0 + 0.1 + dur + FRAME);
    tl.fromTo(c, { scale: 0.9 }, { scale: 1.06, duration: t1 - t0, ease: "sine.inOut" }, t0);
    spec.impacts_extra.push(t0 + 0.1 + dur);
  };

  C["end-card"] = function (d, t0, t1) {
    const e = el("div", "endcard", gfxL);
    const q = el("div", "end-q", e, { text: d.prompt });
    const p = el("div", "end-pill", e, { text: "TELL ME IN THE COMMENTS" });
    tl.fromTo(q, { x: 200, opacity: 0 }, { x: 0, opacity: 1, duration: 0.35, ease: "back.out(1.7)" }, t0 + 0.2);
    tl.fromTo(p, { scale: 0 }, { scale: 1, duration: 0.3, ease: "back.out(3)" }, t0 + 0.7);
    tl.to(p, { scale: 1.08, duration: 0.3, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0 - 1.2) / 0.3)), ease: "sine.inOut" }, t0 + 1.0);
  };

  /* ---------- maps ---------- */
  const WORLD_PLACES = {
    USA: [-98, 39], Nevada: [-115.7, 36.6], "Middle East": [44, 33], Afghanistan: [66, 34], Iran: [53, 32.5],
    Russia: [52.1, 55.8], Ukraine: [31.2, 49], "Nagorno-Karabakh": [46.7, 39.8], "Black Sea": [34, 43.3],
    Lebanon: [35.9, 33.9], Turkey: [35, 39], Israel: [35, 31.5], MDV: [73.5, 3.2], Libya: [17.5, 27.5],
  };
  function proj(p) { return [((p[0] + 180) / 360) * 2000, ((90 - p[1]) / 180) * 1000]; }
  function drawWorld(svg, hi) {
    const g = sv("g", svg, {});
    const out = {};
    for (const name in (window.WORLD || {})) {
      const path = sv("path", g, { d: WORLD[name], class: "land", "data-n": name });
      out[name] = path;
    }
    return out;
  }
  function ping(svg, x, y, at, n, rmax, sw) {
    sv("circle", svg, { cx: x, cy: y, r: rmax / 8, fill: "#ff5a1f" });
    for (let i = 0; i < n; i++) {
      const c = sv("circle", svg, { cx: x, cy: y, r: 1, fill: "none", stroke: "#ff5a1f", "stroke-width": sw });
      tl.fromTo(c, { attr: { r: 1 }, opacity: 1 }, { attr: { r: rmax }, opacity: 0, duration: 0.8, ease: "power2.out" }, at + i * 0.35);
    }
  }
  function mapLabel(svg, x, y, text, size, at) {
    const t = sv("text", svg, { x, y, class: "lbl", "font-size": size, "text-anchor": "middle", text: text.toUpperCase(),
      stroke: "#000", "stroke-width": size / 9, "paint-order": "stroke" });
    tl.fromTo(t, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.25, ease: "back.out(2)" }, at);
    return t;
  }
  function viewTo(svg, cx, cy, w, at, dur, w0) {
    const h = w * 0.5625;
    const set = (ww) => ({ attr: { viewBox: (cx - ww / 2) + " " + (cy - (ww * 0.5625) / 2) + " " + ww + " " + ww * 0.5625 } });
    tl.fromTo(svg, set(w0 || w * 1.4), Object.assign(set(w), { duration: dur, ease: "power2.inOut" }), at);
    return h;
  }

  C["map-arc"] = function (d, t0, t1) {
    el("div", "fill bg-grid", gfxL); /* opaque: a map never lets the photo behind it show through */
    const { svg } = svgLayer(gfxL, "0 0 2000 1000");
    drawWorld(svg);
    const pts = [d.from, d.via, d.to].filter(Boolean).map((n) => proj(WORLD_PLACES[n]));
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), (Math.max(...ys) - Math.min(...ys)) * 1.78, 120) * 1.7;
    viewTo(svg, cx, cy, span, t0, t1 - t0, span * 1.35);
    const per = (t1 - t0 - 0.8) / (pts.length - 1);
    const sw = span / 260;
    [d.from, d.via, d.to].filter(Boolean).forEach((n, i) => {
      const [x, y] = pts[i];
      ping(svg, x, y, t0 + 0.2 + i * per, 2, span / 22, sw);
      mapLabel(svg, x, y - span / 40, n, span / 30, t0 + 0.25 + i * per);
    });
    for (let i = 0; i < pts.length - 1; i++) {
      const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2 - Math.hypot(x2 - x1, y2 - y1) * 0.35;
      const p = sv("path", svg, { d: `M${x1},${y1} Q${mx},${my} ${x2},${y2}`, fill: "none", stroke: "#ffd23f", "stroke-width": sw * 1.4, "stroke-dasharray": "2000", "stroke-dashoffset": "2000", "stroke-linecap": "round" });
      tl.to(p, { attr: { "stroke-dashoffset": 0 }, duration: per * 0.9, ease: "power2.inOut" }, t0 + 0.3 + i * per);
    }
    if (d.card) C["name-card"](d.card, t0 + 0.4, t1);
  };

  C["world-map"] = function (d, t0, t1) {
    el("div", "fill bg-grid", gfxL);
    const { svg } = svgLayer(gfxL, "0 0 2000 1000");
    const paths = drawWorld(svg);
    if (d.highlight) {
      /* The headline figure shows from the first frame: it is what the voice says. Only
         countries a source names are lit; the home country is lit in its own colour. */
      const list = spec.highlight_names || [];
      const home = spec.highlight_home;
      viewTo(svg, 1100, 380, 1250, t0, t1 - t0, 1700);
      if (home && paths[home]) tl.set(paths[home], { fill: "#ffd23f" }, t0);
      const buyers = list.filter((n) => n !== home);
      const step = Math.min(0.12, (t1 - t0 - 1.0) / buyers.length);
      buyers.forEach((n, i) => {
        const at = t0 + 0.3 + i * step;
        if (paths[n]) tl.to(paths[n], { fill: "#ff5a1f", duration: 0.1 }, at);
        else if (WORLD_PLACES[n]) { const [x, y] = proj(WORLD_PLACES[n]); ping(svg, x, y, at, 1, 25, 3); }
      });
      const cnt = el("div", "kin top", gfxL); const tx = el("div", "kin-text", cnt, { text: d.headline || "30+ COUNTRIES" });
      tx.style.fontSize = "58px";
      tl.set(tx, { scale: 1.4 }, t0).to(tx, { scale: 1, duration: 0.25, ease: "back.out(3)" }, t0 + FRAME);
      if (d.footnote) {
        const fn = el("div", "map-foot", gfxL, { text: d.footnote });
        tl.set(fn, { opacity: 0 }, t0).to(fn, { opacity: 1, duration: 0.3 }, t0 + 0.3 + buyers.length * step);
      }
    }
    if (d.locator) {
      const [x, y] = proj(WORLD_PLACES[d.locator]);
      viewTo(svg, x, y, 260, t0, Math.min(1.6, t1 - t0), 1600);
      ping(svg, x, y, t0 + 1.2, 3, 22, 1.5);
      mapLabel(svg, x, y - 16, d.locator, 13, t0 + 1.3);
      if (d.year) mapLabel(svg, x, y + 30, String(d.year), 11, t0 + 1.5);
      if (spec.silhouette) {
        const g = sv("g", svg, {});
        sv("path", g, { d: DRONE_FIXED, fill: "#fff", transform: "scale(0.12)" });
        tl.fromTo(g, { attr: { transform: `translate(${x - 120},${y - 50}) rotate(12)` } }, { attr: { transform: `translate(${x + 120},${y + 10}) rotate(12)` }, duration: t1 - t0 - 1.2, ease: "none" }, t0 + 1.1);
      }
      if (d.event === "ships sunk") {
        [[-30, 8], [6, 18], [34, 4]].forEach(([dx, dy], i) => {
          const s = sv("g", svg, {});
          sv("path", s, { d: "M-10,0 L10,0 L7,4 L-7,4 Z M-3,-5 L3,-5 L3,0 L-3,0 Z", fill: "#cfd6df", stroke: "#000", "stroke-width": 0.6 });
          const tx0 = `translate(${x + dx},${y + dy})`;
          tl.set(s, { attr: { transform: tx0 } }, t0);
          const at = t0 + 1.8 + i * ((t1 - t0 - 2.4) / 3);
          tl.fromTo(s, { attr: { transform: tx0 + " rotate(0)" }, opacity: 1 }, { attr: { transform: `translate(${x + dx},${y + dy + 8}) rotate(${i % 2 ? 35 : -35})` }, opacity: 0, duration: 0.9, ease: "power2.in" }, at);
          spec.impacts_extra.push(at);
        });
      }
    }
  };

  /* ---------- diagrams ---------- */
  const DRONE_QUAD = "M-60,-8 L60,-8 L60,8 L-60,8 Z M-8,-60 L8,-60 L8,60 L-8,60 Z";
  const DRONE_FIXED = "M0,-6 L220,-14 L240,-4 L240,4 L220,14 L0,6 Z M90,-6 L120,-140 L150,-140 L140,-6 Z M90,6 L120,140 L150,140 L140,6 Z M200,-8 L215,-60 L232,-60 L228,-8 Z M200,8 L215,60 L232,60 L228,8 Z";
  function quad(svg, x, y, s, color) {
    /* the caller animates the returned inner group; the outer one keeps the placement */
    const outer = sv("g", svg, { transform: `translate(${x},${y})` });
    const g = sv("g", outer, {});
    const art = sv("g", g, { transform: `scale(${s})` });
    sv("rect", art, { x: -18, y: -12, width: 36, height: 24, rx: 5, fill: color || "#e8edf3" });
    [[-48, -34], [48, -34], [-48, 34], [48, 34]].forEach(([a, b]) => {
      sv("line", art, { x1: 0, y1: 0, x2: a, y2: b, stroke: color || "#e8edf3", "stroke-width": 7 });
      sv("ellipse", art, { cx: a, cy: b, rx: 26, ry: 5, fill: "rgba(255,255,255,0.35)" });
    });
    return g;
  }
  function radar(svg, x, y) {
    const g = sv("g", svg, { transform: `translate(${x},${y})` });
    sv("path", g, { d: "M-16,10 L16,10 L8,0 L-8,0 Z", fill: "#8e9bab" });
    sv("path", g, { d: "M-14,-2 Q0,-26 14,-2", fill: "none", stroke: "#cfd6df", "stroke-width": 4 });
    return g;
  }
  function jet(svg) {
    const g = sv("g", svg, {});
    sv("path", g, { d: "M40,0 L-20,-6 L-30,-26 L-38,-26 L-34,-6 L-44,-4 L-50,-14 L-56,-14 L-54,0 L-56,14 L-50,14 L-44,4 L-34,6 L-38,26 L-30,26 L-20,6 Z", fill: "#e8edf3" });
    return g;
  }
  function label(svg, x, y, text, size, at, cls, color) {
    const t = sv("text", svg, { x, y, class: cls || "lbl", "font-size": size || 22, "text-anchor": "middle", fill: color || "#fff", text });
    tl.fromTo(t, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.2, ease: "back.out(2)" }, at);
    return t;
  }
  function cross(svg, x, y, at) {
    const g = sv("g", svg, { transform: `translate(${x},${y})` });
    const a = sv("line", g, { x1: -18, y1: -18, x2: 18, y2: 18, stroke: "#ff2d3a", "stroke-width": 7, "stroke-linecap": "round" });
    const b = sv("line", g, { x1: 18, y1: -18, x2: -18, y2: 18, stroke: "#ff2d3a", "stroke-width": 7, "stroke-linecap": "round" });
    tl.fromTo([a, b], { opacity: 0, scale: 2.5, transformOrigin: "50% 50%" }, { opacity: 1, scale: 1, duration: 0.14, stagger: 0.06, ease: "power3.in" }, at);
  }

  const D = {};
  D["fpv-payload"] = function (svg, d, t0, t1) {
    const q = quad(svg, 480, 230, 2.2);
    const nade = sv("g", sv("g", svg, { transform: "translate(480,330)" }), {});
    sv("ellipse", nade, { cx: 0, cy: 0, rx: 22, ry: 30, fill: "#6b7a3a", stroke: "#000", "stroke-width": 3 });
    sv("rect", nade, { x: -8, y: -42, width: 16, height: 14, fill: "#3d4421" });
    const strap = sv("line", svg, { x1: 480, y1: 250, x2: 480, y2: 300, stroke: "#ffd23f", "stroke-width": 4, "stroke-dasharray": "6 5" });
    tl.fromTo(q, { opacity: 0 }, { opacity: 1, duration: 0.2 }, t0);
    tl.fromTo(nade, { opacity: 0, y: -60 }, { opacity: 1, y: 0, duration: 0.3, ease: "bounce.out" }, t0 + 0.4);
    tl.fromTo(strap, { opacity: 0 }, { opacity: 1, duration: 0.1 }, t0 + 0.55);
    const c1 = sv("path", svg, { d: "M560,200 L680,140 L800,140", fill: "none", stroke: "#3fd0ff", "stroke-width": 3 });
    const c2 = sv("path", svg, { d: "M505,340 L640,400 L780,400", fill: "none", stroke: "#ff5a1f", "stroke-width": 3 });
    [c1, c2].forEach((c, i) => tl.fromTo(c, { attr: { "stroke-dasharray": "400", "stroke-dashoffset": 400 } }, { attr: { "stroke-dashoffset": 0 }, duration: 0.3 }, t0 + 0.3 + i * 0.4));
    label(svg, 740, 128, "RACING DRONE", 26, t0 + 0.5, "lbl", "#3fd0ff");
    label(svg, 720, 390, "GRENADE", 26, t0 + 0.9, "lbl", "#ff5a1f");
    for (let i = 0; i < 6; i++) tl.to(q, { y: i % 2 ? -4 : 4, duration: (t1 - t0) / 6, ease: "sine.inOut" }, t0 + (i * (t1 - t0)) / 6);
  };

  D["bekaa-1982"] = function (svg, d, t0, t1) {
    const steps = d.steps || [1, 2, 3];
    const ground = sv("path", svg, { d: "M0,420 C200,400 300,440 480,420 C660,400 760,440 960,420 L960,540 L0,540 Z", fill: "#1d2633" });
    label(svg, 480, 395, "BEKAA VALLEY · 1982", 24, t0 + 0.1, "lbl-s", "#aab4c2");
    const radars = [[300, 410], [470, 405], [640, 412], [780, 408]].map(([x, y]) => [x, y, radar(svg, x, y)]);
    const span = t1 - t0;
    if (steps.includes(1)) {
      label(svg, 210, 90, "1  DECOY DRONES", 24, t0 + 0.2, "lbl", "#3fd0ff");
      for (let i = 0; i < 4; i++) {
        const g = sv("g", svg, {});
        sv("path", g, { d: DRONE_FIXED, fill: "#3fd0ff", transform: "scale(0.16)" });
        tl.fromTo(g, { attr: { transform: `translate(${-80 - i * 70},${150 + i * 28})` } }, { attr: { transform: `translate(${560 + i * 70},${150 + i * 28})` }, duration: span * 0.7, ease: "none" }, t0 + 0.1 + i * 0.12);
      }
    }
    if (steps.includes(2)) {
      const at = t0 + span * 0.5;
      label(svg, 740, 90, "2  RADARS SWITCH ON", 24, at, "lbl", "#ffd23f");
      radars.forEach(([x, y], i) => {
        for (let k = 0; k < 2; k++) {
          const c = sv("circle", svg, { cx: x, cy: y - 10, r: 2, fill: "none", stroke: "#ffd23f", "stroke-width": 3 });
          tl.fromTo(c, { attr: { r: 2 }, opacity: 1 }, { attr: { r: 90 }, opacity: 0, duration: 0.7, ease: "power2.out" }, at + i * 0.12 + k * 0.4);
        }
      });
    }
    if (steps.includes(3)) {
      label(svg, 480, 90, "3  JETS STRIKE", 30, t0 + 0.2, "lbl", "#ff2d3a");
      for (let j = 0; j < 3; j++) {
        const g = jet(svg);
        tl.fromTo(g, { attr: { transform: `translate(-80,${170 + j * 40}) scale(1.4)` } }, { attr: { transform: `translate(1060,${120 + j * 40}) scale(1.4)` }, duration: span * 0.5, ease: "power1.in" }, t0 + 0.3 + j * 0.15);
      }
      radars.forEach(([x, y], i) => {
        const at = t0 + 0.6 + span * 0.25 + i * 0.25;
        if (i < 3) { cross(svg, x, y - 10, at); spec.impacts_extra.push(at); }
      });
    }
  };

  D["loiter-dive"] = function (svg, d, t0, t1) {
    sv("rect", svg, { x: 0, y: 0, width: 960, height: 540, fill: "rgba(11,13,18,0.55)" });
    const span = t1 - t0;
    const tx = 690, ty = 440;
    radar(svg, tx, ty);
    const orbit = sv("ellipse", svg, { cx: tx, cy: 200, rx: 130, ry: 40, fill: "none", stroke: "rgba(255,255,255,0.35)", "stroke-width": 2, "stroke-dasharray": "6 6" });
    tl.fromTo(orbit, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t0 + 0.4);
    const g = sv("g", svg, {});
    sv("path", g, { d: DRONE_FIXED, fill: "#ff5a1f", transform: "scale(0.14) translate(-120,0)" });
    const n = 14, loopT = span * 0.55;
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      tl.set(g, { attr: { transform: `translate(${tx + Math.cos(a) * 130},${200 + Math.sin(a) * 40}) rotate(${(a * 180) / Math.PI + 90})` } }, t0 + 0.2 + (i * loopT) / n);
    }
    tl.fromTo(g, { attr: { transform: `translate(${tx + 130},200) rotate(90)` } }, { attr: { transform: `translate(${tx},${ty - 14}) rotate(90)` }, duration: 0.35, ease: "power3.in" }, t0 + 0.25 + loopT);
    spec.impacts_extra.push(t0 + 0.6 + loopT);
    label(svg, 240, 140, "LAUNCH", 28, t0 + 0.2, "lbl", "#3fd0ff");
    label(svg, 240, 190, "LOITER  (HOURS)", 28, t0 + 0.6, "lbl", "#ffd23f");
    label(svg, 240, 240, "DIVE ON THE RADAR", 28, t0 + 0.25 + loopT, "lbl", "#ff2d3a");
  };

  D["fpv-jam-vs-fibre"] = function (svg, d, t0, t1) {
    const span = t1 - t0, mid = t0 + span * 0.45;
    const pilot = sv("g", svg, { transform: "translate(150,360)" });
    sv("circle", pilot, { cx: 0, cy: -60, r: 22, fill: "#e8edf3" });
    sv("rect", pilot, { x: -26, y: -36, width: 52, height: 80, rx: 12, fill: "#e8edf3" });
    sv("rect", pilot, { x: -22, y: -70, width: 44, height: 16, rx: 4, fill: "#111" });
    const q = quad(svg, 800, 200, 1.1);
    const wave = sv("path", svg, { d: "M190,300 Q260,240 330,290 T470,280 T610,250 T740,215", fill: "none", stroke: "#3fd0ff", "stroke-width": 5, "stroke-dasharray": "14 10" });
    tl.fromTo(wave, { attr: { "stroke-dashoffset": 0 } }, { attr: { "stroke-dashoffset": -240 }, duration: span * 0.45, ease: "none" }, t0);
    label(svg, 480, 90, "RADIO LINK", 30, t0 + 0.1, "lbl", "#3fd0ff");
    const jam = sv("g", sv("g", svg, { transform: "translate(470,450)" }), {});
    sv("rect", jam, { x: -30, y: -20, width: 60, height: 40, fill: "#ff2d3a" });
    sv("line", jam, { x1: 0, y1: -20, x2: 0, y2: -60, stroke: "#ff2d3a", "stroke-width": 5 });
    tl.fromTo(jam, { opacity: 0, scale: 0.4, transformOrigin: "50% 50%" }, { opacity: 1, scale: 1, duration: 0.2, ease: "back.out(3)" }, t0 + span * 0.2);
    for (let k = 0; k < 3; k++) {
      const c = sv("circle", svg, { cx: 470, cy: 390, r: 4, fill: "none", stroke: "#ff2d3a", "stroke-width": 4 });
      tl.fromTo(c, { attr: { r: 4 }, opacity: 1 }, { attr: { r: 200 }, opacity: 0, duration: 0.6 }, t0 + span * 0.25 + k * 0.2);
    }
    tl.to(wave, { opacity: 0, duration: 0.05 }, t0 + span * 0.35);
    cross(svg, 470, 270, t0 + span * 0.35);
    const jl = label(svg, 480, 200, "JAMMED", 44, t0 + span * 0.35, "lbl", "#ff2d3a");
    tl.to(jl, { opacity: 0, duration: 0.1 }, mid);
    const fibre = sv("path", svg, { d: "M190,320 C350,420 520,160 780,215", fill: "none", stroke: "#ffd23f", "stroke-width": 4, "stroke-dasharray": "900", "stroke-dashoffset": "900" });
    tl.to(fibre, { attr: { "stroke-dashoffset": 0 }, duration: span * 0.3, ease: "power2.out" }, mid);
    const fl = label(svg, 480, 140, "FIBRE-OPTIC CABLE: NOTHING TO JAM", 34, mid + 0.2, "lbl", "#ffd23f");
    tl.set(q, { opacity: 1 }, t0);
    for (let i = 0; i < 6; i++) tl.to(q, { y: i % 2 ? -5 : 5, duration: span / 6, ease: "sine.inOut" }, t0 + (i * span) / 6);
  };

  C["diagram"] = function (d, t0, t1) {
    const { svg } = svgLayer(gfxL);
    if (d.card) C["name-card"](d.card, t0, t0 + Math.min(t1 - t0, 3.2));
    const dt0 = d.card ? t0 + (d.after || 0) : t0;
    if (D[d.name]) D[d.name](svg, d, dt0, t1);
  };

  C["swarm"] = function (d, t0, t1) {
    const { svg } = svgLayer(gfxL);
    const r2 = rng(d.seed || 1);
    const n = 64, dots = [], lines = [];
    const form = [];
    for (let i = 0; i < n; i++) {
      const row = Math.floor(i / 8), col = i % 8;
      form.push([480 + (col - 3.5) * 42 + (row % 2) * 21, 270 + (row - 3.5) * 30]);
    }
    for (let i = 0; i < n; i++) {
      const c = sv("circle", svg, { cx: 0, cy: 0, r: 5, fill: "#3fd0ff" });
      const p0 = [r2() * 960, r2() * 540], p1 = [r2() * 960, r2() * 540];
      tl.fromTo(c, { attr: { cx: p0[0], cy: p0[1] } }, { attr: { cx: p1[0], cy: p1[1] }, duration: (t1 - t0) * 0.4, ease: "sine.inOut" }, t0);
      tl.to(c, { attr: { cx: form[i][0], cy: form[i][1] }, duration: (t1 - t0) * 0.3, ease: "power3.inOut" }, t0 + (t1 - t0) * 0.4);
      dots.push(c);
    }
    for (let i = 0; i < n; i++) {
      const j = i + 1, k = i + 8;
      [j, k].forEach((m) => {
        if (m >= n || (m === j && j % 8 === 0)) return;
        const l = sv("line", svg, { x1: form[i][0], y1: form[i][1], x2: form[m][0], y2: form[m][1], stroke: "rgba(63,208,255,0.5)", "stroke-width": 1.5, opacity: 0 });
        lines.push(l);
      });
    }
    tl.to(lines, { opacity: 1, duration: 0.4, stagger: 0.004 }, t0 + (t1 - t0) * 0.72);
    tl.to(dots, { attr: { fill: "#ffd23f" }, duration: 0.2 }, t0 + (t1 - t0) * 0.72);
  };

  C["timeline"] = function (d, t0, t1) {
    const items = spec.timeline_items || [];
    const gap = 190, strip = el("div", "tl-strip", gfxL);
    const width = items.length * gap + 200;
    strip.style.width = width + "px";
    const axis = el("div", "tl-axis", strip); axis.style.width = width + "px";
    items.forEach((it, i) => {
      const n = el("div", "tl-item", strip); n.style.left = 100 + i * gap + "px";
      el("div", "tl-dot", n);
      const up = i % 2 === 0;
      const y = el("div", "tl-year", n, { text: String(it.year) }); y.style.top = (up ? 250 : 322) + "px";
      const nm = el("div", "tl-name", n, { text: it.name }); nm.style.top = (up ? 214 : 360) + "px";
      if (it.src) { const im = el("img", "tl-img", n, { src: it.src, alt: "" }); im.style.top = (up ? 118 : 404) + "px"; }
      tl.fromTo(n, { opacity: 0, y: up ? -30 : 30 }, { opacity: 1, y: 0, duration: 0.2, ease: "back.out(2)" }, t0 + 0.05 + i * 0.12);
    });
    /* fast zoom out from 1918, then a steady travel to today: readable the whole way */
    const s = 0.62;
    const travel = -(width * s - 960 + 40);
    tl.fromTo(strip, { x: 0, scale: 1.3, transformOrigin: "0% 55%" }, { x: 0, scale: s, duration: 0.9, ease: "power3.inOut" }, t0 + 0.3);
    tl.to(strip, { x: travel, duration: Math.max(0.5, t1 - t0 - 1.5), ease: "power1.inOut" }, t0 + 1.2);
  };

  /* ---------- presenter ---------- */
  function presenter() {
    const P = spec.presenter;
    if (!P) return;
    const outer = el("div", "pres", presL);
    outer.style.left = P.x + "px"; outer.style.top = P.y + "px";
    outer.style.width = P.w + "px"; outer.style.height = P.h + "px";
    const shadow = el("div", "pres-shadow", outer); shadow.style.left = P.w * 0.15 + "px"; shadow.style.width = P.w * 0.7 + "px"; shadow.style.top = P.h - 8 + "px";
    const sq = el("div", "pres-squash", outer); sq.style.width = P.w + "px"; sq.style.height = P.h + "px";
    const body = el("div", "pres-body", sq); body.style.width = P.w + "px"; body.style.height = P.h + "px";
    if (P.flip) body.style.transform = "scaleX(-1)";
    el("img", "pres-part", body, { src: P.pose, alt: "", style: { left: "0px", top: "0px", width: P.w + "px", height: P.h + "px" } });
    const put = (part) => el("img", "pres-part", body, { src: part.src, alt: "", style: {
      left: part.x + "px", top: part.y + "px", width: part.w + "px", height: part.h + "px",
      transform: (part.flip ? "scaleX(-1) " : "") + (part.rot ? "rotate(" + part.rot + "deg)" : "") } });
    P.eyes.forEach(put); if (P.nose) put(P.nose);
    const closed = (P.eyes_closed || []).map(put);
    const openEyes = [...body.querySelectorAll("img")].slice(1, 1 + P.eyes.length);
    tl.set(closed, { opacity: 0 }, 0);
    (P.blinks || []).forEach((t) => {
      tl.set(openEyes, { opacity: 0 }, t).set(closed, { opacity: 1 }, t);
      tl.set(openEyes, { opacity: 1 }, t + 3 * FRAME).set(closed, { opacity: 0 }, t + 3 * FRAME);
    });
    const mouths = {};
    Object.keys(P.mouths).forEach((k) => { mouths[k] = put(P.mouths[k]); tl.set(mouths[k], { opacity: 0 }, 0); });
    let cur = null;
    (P.mouth_track || []).forEach(([t, k]) => {
      if (k === cur) return;
      if (cur) tl.set(mouths[cur], { opacity: 0 }, t);
      tl.set(mouths[k], { opacity: 1 }, t);
      cur = k;
    });

    /* squash and stretch: one pose, never tweened into another */
    const ent = P.entrance || "pop";
    const t0 = P.t0 || 0;
    const from = ent === "left" ? { x: -P.x - P.w, y: -40 } : ent === "right" ? { x: W - P.x + 40, y: -40 } : ent === "drop" ? { x: 0, y: -H } : { x: 0, y: 40 };
    tl.fromTo(outer, Object.assign({ opacity: ent === "pop" ? 0 : 1 }, from), { x: 0, y: 0, opacity: 1, duration: 0.24, ease: "power2.in" }, t0);
    tl.fromTo(sq, { scaleX: 0.7, scaleY: 1.35 }, { scaleX: 1.3, scaleY: 0.72, duration: 0.24, ease: "power2.in" }, t0);
    tl.to(sq, { scaleX: 0.9, scaleY: 1.12, duration: 0.1, ease: "power2.out" }, t0 + 0.24);
    tl.to(sq, { scaleX: 1, scaleY: 1, duration: 0.35, ease: "elastic.out(1.1, 0.4)" }, t0 + 0.34);
    let t = t0 + 0.7;
    const hits = (P.hits || []).filter((h) => h > t).sort((a, b) => a - b);
    const end = DUR - 0.05;
    while (t < end) {
      const nh = hits.find((h) => h >= t);
      if (nh !== undefined && nh - t < 0.45) {
        tl.to(sq, { scaleX: 1.16, scaleY: 0.84, duration: Math.max(FRAME, Math.min(0.07, nh - t)), ease: "power2.in" }, t);
        tl.to(sq, { scaleX: 0.9, scaleY: 1.14, duration: 0.08, ease: "power2.out" }, Math.max(t, nh));
        tl.to(sq, { scaleX: 1, scaleY: 1, duration: 0.25, ease: "elastic.out(1, 0.45)" }, Math.max(t, nh) + 0.08);
        tl.to(body, { rotation: rr(-4, 4), duration: 0.1 }, Math.max(t, nh));
        t = Math.max(t, nh) + 0.36;
        hits.splice(hits.indexOf(nh), 1);
        continue;
      }
      const d = Math.min(0.42, end - t);
      if (d < 0.05) break;
      const up = Math.round((t - t0) / 0.42) % 2 === 0;
      tl.to(sq, { scaleX: up ? 0.98 : 1.02, scaleY: up ? 1.035 : 0.975, duration: d, ease: "sine.inOut" }, t);
      tl.to(body, { rotation: up ? 1.2 : -1.2, duration: d, ease: "sine.inOut" }, t);
      t += d;
    }
    if (P.bounce) tl.to(outer, { y: -26, duration: 0.18, yoyo: true, repeat: Math.max(1, Math.floor((DUR - t0 - 0.8) / 0.18)), ease: "power1.out" }, t0 + 0.6);
  }

  /* ---------- music notes (s20) ---------- */
  function notes() {
    if (!spec.notes) return;
    const L = el("div", "notes", gfxL);
    const glyphs = ["♪", "♫", "♬", "♩"];
    for (let i = 0; i < 14; i++) {
      const n = el("div", "note", L, { text: glyphs[i % 4] });
      n.style.left = 480 + "px"; n.style.top = 300 + "px";
      const a = R() * Math.PI * 2, r = rr(180, 420);
      tl.fromTo(n, { x: 0, y: 0, scale: 0.2, opacity: 1, rotation: 0 }, { x: Math.cos(a) * r, y: Math.sin(a) * r * 0.6, scale: rr(0.8, 1.6), rotation: rr(-50, 50), opacity: 0, duration: rr(0.9, 1.6), ease: "power2.out" }, rr(0.1, DUR - 1.2));
    }
  }

  /* ---------- subtitles ---------- */
  function subtitles() {
    const S = el("div", "subs", hudL);
    (spec.captions || []).forEach((g) => {
      const row = el("div", "sub-group", S);
      tl.set(row, { opacity: 1 }, Math.max(0, g.t0)).set(row, { opacity: 0 }, Math.min(DUR, g.t1));
      g.words.forEach((w) => {
        const s = el("span", "sub-w" + (w.shout ? " shout" : ""), row, { text: w.w });
        /* Emphasis moves vertically only. A shouted word is set bigger in the layout itself
           (.shout), so its room is reserved; nothing grows sideways into a neighbour. */
        tl.set(s, { opacity: 0.55, y: 0 }, Math.max(0, g.t0));
        tl.set(s, { opacity: 1, y: w.shout ? -14 : -6 }, Math.max(0, w.t0));
        tl.to(s, { y: 0, duration: w.shout ? 0.22 : 0.12, ease: "back.out(3)" }, Math.max(0, w.t0) + FRAME);
        /* never place a tween before 0: GSAP would shift the whole timeline later to fit it */
        if (w.shout && w.t0 >= 0) {
          for (let i = 0; i < 4; i++) tl.to(s, { y: rr(-4, 4), duration: FRAME }, w.t0 + 0.25 + i * FRAME);
          tl.to(s, { y: 0, duration: FRAME }, w.t0 + 0.25 + 4 * FRAME);
        }
      });
    });
  }

  /* ---------- HUD year ticker ---------- */
  function hudTicker() {
    if (!spec.ticker) return;
    const { t, strips } = tickerDom(hudL, "ticker", spec.ticker.to);
    rollTicker(strips, spec.ticker.from, spec.ticker.to, 0.05, 0.6, 34);
    tl.fromTo(t, { x: spec.ticker.enter ? -160 : 0 }, { x: 0, duration: 0.3, ease: "back.out(2)" }, 0);
  }

  /* ---------- impacts: 6-frame shake + white flash ---------- */
  function impacts() {
    const fl = el("div", "fill flash", fxL);
    const r2 = rng(hash(spec.id + "shake"));
    const list = [...(spec.impacts || []), ...spec.impacts_extra].filter((t) => t >= 0 && t < DUR).sort((a, b) => a - b);
    tl.set(fl, { opacity: 0 }, 0);
    list.forEach((t) => {
      for (let i = 0; i < 6; i++) tl.set(shakeL, { x: (r2() - 0.5) * 26 * (1 - i / 6), y: (r2() - 0.5) * 18 * (1 - i / 6) }, t + i * FRAME);
      tl.set(shakeL, { x: 0, y: 0 }, t + 6 * FRAME);
      tl.set(fl, { opacity: spec.flash === false ? 0 : 0.85 }, t);
      tl.to(fl, { opacity: 0, duration: 4 * FRAME, ease: "power1.out" }, t + FRAME);
    });
  }

  /* ---------- texture: grain + vignette, seeked, never clocked ---------- */
  function texture() {
    el("div", "fill vignette", fxL);
    if (spec.grain) {
      const g = el("div", "fill grain", fxL);
      g.style.backgroundImage = "url(" + spec.grain + ")";
      const n = Math.ceil(DUR / (2 * FRAME));
      const r2 = rng(hash(spec.id + "grain"));
      for (let i = 0; i < n; i++) tl.set(g, { backgroundPosition: Math.round(r2() * 256) + "px " + Math.round(r2() * 256) + "px" }, i * 2 * FRAME);
    }
    if (spec.scan) el("div", "fill scan", fxL);
  }

  spec.impacts_extra = [];
  background();
  (spec.graphics || []).forEach((g) => {
    const f = C[g.component];
    if (!f) return;
    const gt0 = clamp(g.t0 || 0), gt1 = g.t1 == null ? DUR : Math.min(DUR, g.t1);
    gfxL = el("div", "layer", gfxRoot);
    if (gt0 > 0) tl.set(gfxL, { opacity: 0 }, 0).set(gfxL, { opacity: 1 }, gt0);
    if (gt1 < DUR) tl.set(gfxL, { opacity: 0 }, gt1);
    f(g.data || {}, gt0, gt1);
  });
  gfxL = gfxRoot;
  notes();
  presenter();
  texture();
  impacts();
  hudTicker();
  subtitles();
  tl.set({}, {}, DUR);
  window.__timelines[spec.id] = tl;
})();
