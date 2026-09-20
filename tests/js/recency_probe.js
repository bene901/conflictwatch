// Fuehrt site/app.js in node aus und ruft die Aktualitaetsregel mit echten Daten auf.
// Das DOM wird nur so weit nachgebildet, dass main() sauber in seinen Fehlerzweig laeuft.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function stubEl() {
  const node = {
    textContent: "", hidden: true, className: "", lang: "", href: "", rel: "",
    target: "", dateTime: "", dataset: {},
    append() { return node; }, appendChild() { return node; },
    sort() { return []; }, forEach() {},
  };
  return node;
}

const sandbox = {
  console,
  Intl,
  Date,
  Number,
  Math,
  JSON,
  Set,
  Boolean,
  document: {
    body: { dataset: { mode: "test" } },
    getElementById: () => stubEl(),
    createElement: () => stubEl(),
  },
  fetch: () => Promise.reject(new Error("kein Netz im Test")),
};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;

const appPath = path.join(__dirname, "..", "..", "site", "app.js");
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(appPath, "utf8"), sandbox, { filename: "app.js" });

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = payload.cases.map((c) => ({
  name: c.name,
  onStart: sandbox.ConflictWatchRecency.onStart(c.item, c.source, Date.parse(c.now)),
}));
process.stdout.write(JSON.stringify(out));
