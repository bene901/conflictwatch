// Fuehrt site/map.js in node aus und liest die tatsaechlich erzeugte SVG-Struktur aus.
// Das DOM wird nur so weit nachgebildet, wie map.js es benutzt - keine Bibliothek.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl(tag, ns) {
  return {
    tagName: tag, ns: ns || null, attrs: {}, children: [], listeners: {}, dataset: {},
    parentNode: null, capturedPointer: null,
    textContent: "", className: "", hidden: false, id: "", type: "", checked: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...kids) {
      for (const k of kids) { k.parentNode = this; this.children.push(k); }
      return this;
    },
    appendChild(k) { k.parentNode = this; this.children.push(k); return k; },
    replaceChildren(...kids) {
      for (const old of this.children) old.parentNode = null;
      this.children = kids.slice();
      for (const k of this.children) k.parentNode = this;
    },
    addEventListener(type, fn) { this.listeners[type] = fn; },
    getBoundingClientRect() { return {left: 0, top: 0, width: 1000, height: 510}; },
    closest(selector) {
      if (selector !== "#map-points a") return null;
      let n = this;
      while (n) {
        if (n.tagName === "a" && n.parentNode && n.parentNode.id === "map-points") return n;
        n = n.parentNode;
      }
      return null;
    },
    setPointerCapture(id) { this.capturedPointer = id; },
    releasePointerCapture(id) { if (this.capturedPointer === id) this.capturedPointer = null; },
  };
}

const registry = {};
for (const id of ["map-view", "map-points", "map-events-note", "map-filters", "map-legend"]) {
  registry[id] = makeEl("div");
  registry[id].id = id;
}

const FixedDate = class extends Date {
  static now() { return Date.parse("2026-09-22T19:30:00Z"); }
};
const sandbox = {
  console, Math, Number, String, Boolean, Array, Set, Map, JSON, RegExp, Object,
  Date: FixedDate,
  document: {
    createElementNS: (ns, name) => makeEl(name, ns),
    createElement: (name) => makeEl(name),
    getElementById: (id) => registry[id] || null,
  },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "..", "site", "map.js"), "utf8"),
                sandbox, {filename: "map.js"});

function controls(tag) {
  const found = [];
  const walk = (node) => {
    if (!tag || node.tagName === tag) found.push(node);
    for (const kid of node.children) walk(kid);
  };
  for (const kid of registry["map-filters"].children) walk(kid);
  return found;
}

function inputs() { return controls("input"); }
function byId(id) { return controls(null).find((n) => n.id === id); }

function dump() {
  const markers = registry["map-points"].children.map((a) => ({
    ariaLabel: a.getAttribute("aria-label"),
    href: a.getAttribute("href"),
    role: a.getAttribute("role"),
    tabIndex: a.getAttribute("tabindex"),
    pressed: a.getAttribute("aria-pressed"),
    shapes: a.children.map((s) => ({
      tag: s.tagName,
      cls: s.getAttribute("class"),
      level: s.getAttribute("data-level"),
      r: s.getAttribute("r"),
      cx: s.getAttribute("cx"),
      cy: s.getAttribute("cy"),
      text: s.textContent,
      fontSize: s.getAttribute("font-size"),
      strokeWidth: s.getAttribute("stroke-width"),
    })),
  }));
  return {
    markers: markers,
    selections: selections.slice(),
    note: registry["map-events-note"].textContent,
    legend: {hidden: registry["map-legend"].hidden, text: registry["map-legend"].textContent},
    viewBox: registry["map-view"].getAttribute("viewBox"),
    filters: {
      hidden: registry["map-filters"].hidden,
      boxes: inputs().map((i) => ({
        id: i.id,
        checked: i.checked,
        // Das <span> neben der Checkbox traegt den sichtbaren Text.
        label: (registry["map-filters"].children
          .find((w) => w.children.includes(i)) || {children: []})
          .children.map((c) => c.textContent).join(""),
      })),
      selects: controls("select").map((s) => ({
        id: s.id, value: s.value,
        options: s.children.map((o) => o.value),
      })),
      buttons: controls("button").map((b) => ({id: b.id, label: b.textContent})),
    },
  };
}

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const selections = [];
sandbox.window.ConflictWatchMap.render(payload.items, payload.sources,
  (it) => selections.push(it.id));
const steps = [{step: "initial", result: dump()}];
if (payload.aircraftSnapshot) {
  sandbox.window.ConflictWatchMap.setAircraftSnapshot(payload.aircraftSnapshot,
    (a) => selections.push("flight:" + a.id));
  steps.push({step: "aircraft_loaded", result: dump()});
}
for (const toggle of payload.toggles || []) {
  if (toggle.touchMarkerLabelIncludes) {
    const marker = registry["map-points"].children.find((m) =>
      String(m.getAttribute("aria-label") || "").includes(toggle.touchMarkerLabelIncludes));
    const hit = marker && marker.children.find((s) => s.getAttribute("class") === "map-hit-target");
    if (!marker || !hit) {
      steps.push({step: "touch-marker:" + toggle.touchMarkerLabelIncludes, missing: true, result: dump()});
      continue;
    }
    const vb = registry["map-view"].getAttribute("viewBox").split(" ").map(Number);
    const x = (Number(hit.getAttribute("cx")) - vb[0]) / vb[2] * 1000;
    const y = (Number(hit.getAttribute("cy")) - vb[1]) / vb[3] * 510;
    const base = {
      pointerId: 41, pointerType: "touch", button: 0, target: hit,
      preventDefault() {}, stopPropagation() {},
    };
    registry["map-view"].listeners.pointerdown(Object.assign({}, base, {clientX: x, clientY: y, timeStamp: 100}));
    registry["map-view"].listeners.pointermove(Object.assign({}, base, {clientX: x + 3, clientY: y + 2, timeStamp: 125}));
    registry["map-view"].listeners.pointerup(Object.assign({}, base, {clientX: x + 3, clientY: y + 2, timeStamp: 150}));
    // Ein echter Browser erzeugt nach einem unveränderten Touch-Ziel den Click.
    // Wenn map.js während des kleinen Fingerzitterns neu zeichnet, ist der alte
    // Marker nicht mehr im Layer und genau dieser Click geht verloren.
    if (registry["map-points"].children.includes(marker) && marker.listeners.click) {
      marker.listeners.click({preventDefault() {}, stopPropagation() {}});
    }
    steps.push({step: "touch-marker:" + toggle.touchMarkerLabelIncludes, result: dump()});
    continue;
  }
  if (toggle.event) {
    const fn = registry["map-view"].listeners[toggle.event];
    if (!fn) {
      steps.push({step: "event:" + toggle.event, missing: true, result: dump()});
      continue;
    }
    const ev = Object.assign({
      pointerId: 1, pointerType: "mouse", button: 0,
      clientX: 500, clientY: 255, deltaY: 0, timeStamp: 0,
      preventDefault() {}, stopPropagation() {},
      target: null,
    }, toggle.payload || {});
    fn(ev);
    steps.push({step: "event:" + toggle.event, result: dump()});
    continue;
  }
  if (toggle.markerLabelIncludes) {
    const marker = registry["map-points"].children.find((m) =>
      String(m.getAttribute("aria-label") || "").includes(toggle.markerLabelIncludes));
    if (!marker || !marker.listeners.click) {
      steps.push({step: "marker:" + toggle.markerLabelIncludes, missing: true, result: dump()});
      continue;
    }
    marker.listeners.click({preventDefault() {}, stopPropagation() {}});
    steps.push({step: "marker:" + toggle.markerLabelIncludes, result: dump()});
    continue;
  }
  const el = byId(toggle.id);
  if (!el) {
    steps.push({step: toggle.id, missing: true, result: dump()});
    continue;
  }
  if (el.tagName === "button") {
    el.listeners.click({});
  } else if (el.tagName === "select") {
    el.value = String(toggle.value);
    el.listeners.change({target: el});
  } else {
    el.checked = toggle.checked;
    el.listeners.change({target: el});
  }
  steps.push({step: toggle.id, result: dump()});
}
process.stdout.write(JSON.stringify(steps));
