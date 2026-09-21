// Fuehrt site/map.js in node aus und liest die tatsaechlich erzeugte SVG-Struktur aus.
// Das DOM wird nur so weit nachgebildet, wie map.js es benutzt - keine Bibliothek.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeEl(tag, ns) {
  return {
    tagName: tag, ns: ns || null, attrs: {}, children: [], listeners: {}, dataset: {},
    textContent: "", className: "", hidden: false, id: "", type: "", checked: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...kids) { for (const k of kids) this.children.push(k); return this; },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids.slice(); },
    addEventListener(type, fn) { this.listeners[type] = fn; },
  };
}

const registry = {};
for (const id of ["map-view", "map-points", "map-events-note", "map-filters", "map-legend"]) {
  registry[id] = makeEl("div");
  registry[id].id = id;
}

const sandbox = {
  console, Math, Number, String, Boolean, Array, Set, Map, JSON, RegExp, Object,
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
for (const toggle of payload.toggles || []) {
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
