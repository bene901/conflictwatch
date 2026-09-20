"use strict";
// ConflictWatch V6 – lädt genau eine Datei (data/snapshot.json). DOM nur über textContent.
(function () {
  const STALE_MS = 3 * 3600 * 1000;
  const OFFICIAL_COLORS = new Set(["green", "yellow", "orange", "red"]);
  const STATUS_TEXT = {
    preliminary: "vorläufig (automatisch erstellt)",
    reviewed: "von der Quelle überprüft",
    withdrawn: "von der Quelle zurückgezogen",
    unknown: "nicht angegeben",
  };
  const FETCH_TEXT = { ok: "Abruf in Ordnung", degraded: "Abruf gestört", down: "Abruf ausgefallen" };
  const DATA_TEXT = { fresh: "Daten vorhanden", empty: "keine Einträge", old: "Messwert veraltet", unknown: "noch keine Daten" };
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
  const absFmt = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" });
  const utcFmt = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  const rel = new Intl.RelativeTimeFormat("de", { numeric: "auto" });
  const num = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });

  function relative(ms, now) {
    const diff = (ms - now) / 1000;
    const abs = Math.abs(diff);
    if (abs < 3600) return rel.format(Math.round(diff / 60), "minute");
    if (abs < 86400) return rel.format(Math.round(diff / 3600), "hour");
    return rel.format(Math.round(diff / 86400), "day");
  }
  const when = (iso) => `${absFmt.format(new Date(iso))} (${utcFmt.format(new Date(iso))} UTC)`;
  const displayTime = (it) => Date.parse(it.kind === "event" ? it.occurred_at : it.kind === "report" ? it.published_at : it.observed_at);
  const schemeOf = (src, id) => src.level_schemes.find((s) => s.id === id);

  function onStart(it, src, now) {
    if (it.data_status === "withdrawn") return false;
    if (it.kind === "status" && src.data_state === "old") return false; // veraltete Messung gilt nicht als aktuell
    const lvl = it.level;
    const floor = lvl ? src.highlight.min_levels[lvl.scheme] : undefined;
    if (lvl && floor !== undefined) {
      const ov = schemeOf(src, lvl.scheme).ordered_values;
      if (ov.indexOf(lvl.value) < ov.indexOf(floor)) return false;
    }
    const within = now - displayTime(it) <= src.highlight.window_h * 3600 * 1000;
    const ongoing = src.highlight.include_ongoing && it.ongoing === true && src.fetch_health !== "down";
    return within || ongoing;
  }

  function metricsText(m) {
    const parts = [];
    if (m.magnitude !== undefined && m.magnitude !== null) {
      parts.push(`Magnitude ${num.format(m.magnitude)}${m.magnitude_type ? " (" + m.magnitude_type + ")" : ""}`);
    }
    if (m.depth_km !== undefined && m.depth_km !== null) parts.push(`Tiefe ${num.format(m.depth_km)} km`);
    for (const [k, v] of Object.entries(m)) {
      if (!["magnitude", "magnitude_type", "depth_km"].includes(k) && v !== null) parts.push(`${k}: ${v}`);
    }
    return parts.join(", ");
  }

  function fact(dl, label, value) {
    if (value === null || value === undefined || value === "") return;
    dl.append(el("dt", null, label), el("dd", null, value));
  }

  function renderItem(it, src, now) {
    const li = el("li", "item");
    if (it.level && OFFICIAL_COLORS.has(String(it.level.value).toLowerCase())) {
      li.dataset.color = String(it.level.value).toLowerCase(); // Farbe der Quelle, keine eigene Bewertung
    }
    const det = el("details");
    const sum = el("summary");
    const head = el("span", "head");
    const title = el("span", "title", it.title);
    title.lang = it.lang;
    const meta = el("span", "meta");
    meta.append(el("span", null, src.name));
    const t = el("time", null, relative(displayTime(it), now));
    t.dateTime = new Date(displayTime(it)).toISOString();
    meta.append(t);
    meta.append(el("span", null, it.level ? it.level.label : "ohne Warnstufe"));
    if (it.data_status === "withdrawn") meta.append(el("span", null, "zurückgezogen"));
    head.append(title, meta);
    sum.append(el("span", "bar"), head);
    det.append(sum);

    const dl = el("dl", "facts");
    fact(dl, "Zeitpunkt", when(new Date(displayTime(it)).toISOString()));
    fact(dl, "Ort", it.location.precision === "unknown" ? "nicht angegeben" : it.location.name);
    fact(dl, "Warnstufe", it.level ? it.level.label : "von der Quelle nicht angegeben – keine Entwarnung");
    if (it.level_change) {
      const lc = it.level_change;
      const note = lc.source_changed_at ? `laut Quelle am ${when(lc.source_changed_at)}` : "Zeitpunkt laut Quelle nicht angegeben";
      fact(dl, "Stufenwechsel", `Von ${lc.from.label} auf ${it.level.label}, erkannt zwischen ${when(lc.detected_between[0])} und ${when(lc.detected_between[1])}. ${note}.`);
    }
    fact(dl, "Prüfstatus", STATUS_TEXT[it.data_status]);
    fact(dl, "Messwerte", metricsText(it.metrics));
    if (it.source_updated_at) fact(dl, "Zuletzt geändert laut Quelle", when(it.source_updated_at));
    if (it.provenance === "relayed" && it.original_publisher) fact(dl, "Ursprünglich veröffentlicht von", it.original_publisher);
    det.append(dl);
    const a = el("a", "source-link", `Originalmeldung bei ${src.name} öffnen`);
    a.href = it.url;
    a.rel = "noopener noreferrer";
    a.target = "_blank";
    det.append(a);
    li.append(det);
    return li;
  }

  function renderStatus(items, srcById) {
    const box = $("status");
    const rows = items.filter((it) => it.kind === "status");
    box.hidden = rows.length === 0;
    for (const it of rows) {
      const src = srcById[it.source];
      const row = el("div", "status-row");
      row.append(el("span", null, it.title));
      if (src.data_state === "old") {
        row.append(el("span", "old", `Letzter bekannter Wert: ${it.level ? it.level.label : "–"}, Messung veraltet`));
      } else {
        row.append(el("span", null, it.level ? it.level.label : "kein Wert"));
      }
      box.append(row);
    }
  }

  function renderSources(sources, now) {
    const ul = $("sources");
    for (const s of sources) {
      const li = el("li");
      li.append(el("div", "name", s.name));
      li.append(el("div", "line", `Datenstand: ${s.newest_source_time ? when(s.newest_source_time) : "keine Angabe"}`));
      li.append(el("div", "line", `Letzter erfolgreicher Abruf: ${s.last_success_at ? relative(Date.parse(s.last_success_at), now) : "noch keiner"}`));
      li.append(el("div", "line", `Zustand: ${FETCH_TEXT[s.fetch_health]}, ${DATA_TEXT[s.data_state]}`));
      li.append(el("div", "line", s.coverage_note));
      li.append(el("div", "line", s.attribution));
      ul.append(li);
    }
  }

  function banner(lines) {
    if (!lines.length) return;
    const b = $("banner");
    for (const l of lines) b.append(el("p", null, l));
    b.hidden = false;
  }

  async function main() {
    let res, snap;
    try {
      res = await fetch(`data/snapshot.json?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      snap = await res.json();
      if (snap.schema_version !== "6.0" || !Array.isArray(snap.items) || !Array.isArray(snap.sources)) {
        throw new Error("unbekanntes Datenformat");
      }
    } catch (err) {
      $("stand").textContent = "Daten konnten nicht geladen werden.";
      $("data-state").textContent = "Nicht verfügbar";
      banner([`Die Datei mit den Meldungen ist nicht erreichbar (${err.message}). Bitte die Seite später neu laden.`]);
      return;
    }
    const serverDate = Date.parse(res.headers.get("Date") || "");
    const now = Number.isFinite(serverDate) ? serverDate : Date.now();
    const generated = Date.parse(snap.generated_at);
    $("stand").textContent = `Zuletzt aktualisiert ${relative(generated, now)}, ${when(snap.generated_at)}`;
    $("source-count").textContent = String(snap.sources.length);
    $("entry-count").textContent = String(snap.items.filter((it) => it.kind !== "status").length);
    $("sources-empty").hidden = snap.sources.length > 0;
    $("data-state").textContent = snap.sources.length === 0 ? "Im Aufbau" : now - generated > STALE_MS ? "Veraltet" : snap.sources.some((s) => s.fetch_health !== "ok" || s.data_state === "old") ? "Eingeschränkt" : "Aktuell";
    const releasedIds = new Set(snap.sources.map((s) => s.id));
    for (const card of document.querySelectorAll(".topic[data-source]")) {
      if (!releasedIds.has(card.dataset.source)) continue;
      const label = card.querySelector(".topic-state");
      label.textContent = "Öffentliche Quelle";
      label.classList.add("live");
    }

    const warnings = [];
    if (now - generated > STALE_MS) {
      warnings.push(`Die Seite wurde seit mehr als drei Stunden nicht aktualisiert. Letzter Stand: ${absFmt.format(new Date(generated))}. Aktuelle Meldungen können fehlen.`);
    }
    const srcById = Object.fromEntries(snap.sources.map((s) => [s.id, s]));
    for (const s of snap.sources) {
      if (s.fetch_health === "down") {
        warnings.push(`Abruf von ${s.name} ausgefallen${s.last_success_at ? " seit " + absFmt.format(new Date(s.last_success_at)) : ""}. Angezeigte Einträge dieser Quelle können veraltet sein.`);
      }
    }
    banner(warnings);

    const items = snap.items.filter((it) => srcById[it.source]);
    renderStatus(items, srcById);
    const start = [], rest = [];
    for (const it of items) {
      if (it.kind === "status") continue;
      (onStart(it, srcById[it.source], now) ? start : rest).push(it);
    }
    const byTime = (a, b) => displayTime(b) - displayTime(a);
    start.sort(byTime).forEach((it) => $("list").append(renderItem(it, srcById[it.source], now)));
    rest.sort(byTime).forEach((it) => $("more-list").append(renderItem(it, srcById[it.source], now)));

    const empty = $("empty");
    if (snap.sources.length === 0) {
      empty.textContent = "Noch keine Quelle freigegeben. Jede Quelle läuft zuerst sieben Tage im Testbetrieb, bevor ihre Meldungen hier erscheinen.";
      empty.hidden = false;
    } else if (start.length === 0) {
      empty.textContent = "Im Anzeigezeitraum gibt es keine Meldungen, die die Kriterien der Quellen erfüllen.";
      empty.hidden = false;
    }
    if (rest.length) {
      $("more-summary").textContent = `Ältere oder niedriger eingestufte Einträge (${rest.length})`;
      $("more").hidden = false;
    }
    renderSources(snap.sources, now);
  }

  main();
})();
