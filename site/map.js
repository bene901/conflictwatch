"use strict";
// Geographic positions are taken exclusively from source-supplied event coordinates.
// This module NEVER requests the visitor's location or estimates personal distance.
//
// Zwei Ortsgenauigkeiten, zwei Darstellungen:
//   precision "point"  -> USGS-Erdbeben, punktgenaue Koordinate der Quelle (unveraendert).
//   precision "region" -> GDACS-Zentroid einer Region. Das ist eine UNGEFAEHRE Lage und
//                         ausdruecklich keine Schadensflaeche. Sie wird nie wie ein
//                         punktgenauer Gefahrenort gezeichnet.
// Warnstufen bleiben Einstufungen der Quelle. Dieses Modul leitet daraus keine eigene
// Gefahrenbewertung ab und erfindet keine Schwellen.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796;
  const RAD = Math.PI / 180;
  const CLUSTER_PX = 16;  // Zusammenfassen erst, wenn Marker einander tatsaechlich ueberdecken.
  const HAZARDS = [
    ["wildfire", "Waldbrände"],
    ["flood", "Überschwemmungen"],
    ["tropical_cyclone", "Wirbelstürme"],
  ];
  const HAZARD_ONE = {wildfire: "Waldbrand", flood: "Überschwemmung",
                      tropical_cyclone: "Wirbelsturm"};
  const LEVEL_ORDER = ["Green", "Orange", "Red"];

  function xy(lon, lat) {
    if (!Number.isFinite(lon) || !Number.isFinite(lat) ||
        Math.abs(lon) > 180 || Math.abs(lat) > 90) return null;
    const t = Math.asin(Math.sqrt(3) / 2 * Math.sin(lat * RAD));
    const t2 = t * t, t6 = t2 * t2 * t2, t8 = t6 * t2;
    const x = 2 * Math.sqrt(3) * (lon * RAD) * Math.cos(t) /
      (3 * (A1 + 3 * A2 * t2 + 7 * A3 * t6 + 9 * A4 * t8));
    const y = A1 * t + A2 * t * t2 + A3 * t * t6 + A4 * t * t8;
    return [500 + 170 * x, 255 - 170 * y];
  }

  function svg(name) { return document.createElementNS(NS, name); }

  // "Aus dem juengsten erfolgreichen Abruf" - dieselbe Regel wie in der Liste.
  // Sie sagt nur: die Quelle meldet den Eintrag weiterhin. Kein Beleg fuer Fortdauer.
  function fromLatestFetch(it, src) {
    return Boolean(src && src.last_success_at && it.last_seen_at === src.last_success_at);
  }

  const state = {hidden: new Set(), showOlder: false, items: [], sources: []};

  // Die beiden Genauigkeiten werden ausdruecklich einzeln benannt, nicht ueber eine
  // Variable ausgewaehlt: so bleibt im Quelltext sichtbar und pruefbar, welche
  // Darstellung fuer welche Ortsangabe gilt.
  function locatable(it) {
    return it.kind === "event" && it.location && xy(it.location.lon, it.location.lat);
  }

  function pointEvents(items) {
    return items.filter((it) => locatable(it) && it.location.precision === "point");
  }

  function regionEvents(items) {
    return items.filter((it) => locatable(it) && it.location.precision === "region");
  }

  function link(label, url) {
    const a = svg("a");
    if (typeof url === "string" && /^https:\/\//.test(url)) {
      a.setAttribute("href", url);
      a.setAttribute("target", "_blank");
      a.setAttribute("rel", "noopener noreferrer");
    }
    a.setAttribute("aria-label", label);
    return a;
  }

  function hitArea(pos) {
    const hit = svg("circle");
    hit.setAttribute("cx", pos[0].toFixed(2));
    hit.setAttribute("cy", pos[1].toFixed(2));
    hit.setAttribute("r", "19");
    hit.setAttribute("fill", "transparent");
    return hit;
  }

  function drawPoint(layer, it) {
    const pos = xy(it.location.lon, it.location.lat);
    const label = it.title + ". Quelle: " + it.source +
      ". Ort: " + (it.location.name || "geografische Position laut Quelle");
    const a = link(label + ". Originalmeldung öffnen", it.url);
    const marker = svg("circle");
    marker.setAttribute("cx", pos[0].toFixed(2));
    marker.setAttribute("cy", pos[1].toFixed(2));
    marker.setAttribute("r", "8");
    marker.setAttribute("class", "map-event-point");
    const title = svg("title");
    title.textContent = label;
    a.append(hitArea(pos), marker, title);
    layer.append(a);
  }

  // Gruppiert nur Marker DESSELBEN Gefahrentyps, die einander auf der Karte ueberdecken.
  // Verschiedene Gefahrenarten werden nie zu einem Marker verschmolzen.
  function cluster(events) {
    const groups = [];
    for (const it of events) {
      const pos = xy(it.location.lon, it.location.lat);
      const hazard = it.metrics && it.metrics.hazard_type;
      const near = groups.find((g) => g.hazard === hazard &&
        Math.hypot(g.pos[0] - pos[0], g.pos[1] - pos[1]) <= CLUSTER_PX);
      if (near) {
        near.items.push(it);
      } else {
        groups.push({hazard: hazard, pos: pos, items: [it]});
      }
    }
    return groups;
  }

  function levelSummary(items) {
    const counts = {};
    for (const it of items) {
      const value = it.level ? it.level.value : null;
      if (value) counts[value] = (counts[value] || 0) + 1;
    }
    const present = LEVEL_ORDER.filter((v) => counts[v]);
    return {
      // Hoechste von der QUELLE vergebene Stufe in dieser Gruppe - keine eigene Bewertung.
      top: present.length ? present[present.length - 1] : null,
      text: present.map((v) => counts[v] + "× " + v).join(", "),
    };
  }

  function drawRegion(layer, group) {
    const pos = group.pos;
    const many = group.items.length > 1;
    // Die Gefahrenart steht IMMER im Marker-Text, auch bei einem einzelnen Ereignis:
    // ein Quelltitel wie "Flood in United States" nennt sie, ein anderer nicht.
    const plural = (HAZARDS.find((h) => h[0] === group.hazard) || [null, "Ereignisse"])[1];
    const singular = HAZARD_ONE[group.hazard] || "Ereignis";
    const name = many ? group.items.length + " " + plural :
      singular + ": " + group.items[0].title;
    const level = levelSummary(group.items);
    const stale = group.items.filter((it) => !it.latest).length;
    const parts = [name + " laut GDACS",
                   "ungefähre Lage laut GDACS – keine Schadensfläche"];
    if (level.text) parts.push("Warnstufe laut GDACS: " + level.text);
    if (many) parts.push("An dieser Stelle zusammengefasst, weil sich die Marker überdecken.");
    if (stale) {
      parts.push(stale + (stale === 1 ? " Meldung stammt" : " Meldungen stammen") +
        " nicht aus dem jüngsten Abruf; das ist keine Entwarnung.");
    }
    const label = parts.join(". ") + ".";
    const a = link(label + (many ? "" : " Originalmeldung öffnen"),
                   many ? null : group.items[0].url);
    const marker = svg("circle");
    marker.setAttribute("cx", pos[0].toFixed(2));
    marker.setAttribute("cy", pos[1].toFixed(2));
    marker.setAttribute("r", many ? "13" : "10");
    marker.setAttribute("class", "map-event-region" + (many ? " is-cluster" : "") +
      (group.items.every((it) => !it.latest) ? " is-older" : ""));
    if (level.top) marker.setAttribute("data-level", level.top.toLowerCase());
    a.append(hitArea(pos), marker);
    if (many) {
      const count = svg("text");
      count.setAttribute("x", pos[0].toFixed(2));
      count.setAttribute("y", (pos[1] + 4).toFixed(2));
      count.setAttribute("class", "map-cluster-count");
      count.setAttribute("text-anchor", "middle");
      count.textContent = String(group.items.length);
      a.append(count);
    }
    const title = svg("title");
    title.textContent = label;
    a.append(title);
    layer.append(a);
  }

  function checkbox(box, id, labelText, checked, onChange) {
    const wrap = document.createElement("label");
    wrap.className = "map-filter";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    input.checked = checked;
    input.addEventListener("change", onChange);
    wrap.append(input, document.createElement("span"));
    wrap.children[1].textContent = labelText;
    box.append(wrap);
    return input;
  }

  function renderFilters(box, available, olderCount) {
    box.replaceChildren();
    if (!available.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    for (const [key, labelText] of HAZARDS) {
      if (!available.includes(key)) continue;
      checkbox(box, "map-filter-" + key.replace(/_/g, "-"), labelText,
               !state.hidden.has(key), function (ev) {
        if (ev && ev.target && ev.target.checked === false) state.hidden.add(key);
        else state.hidden.delete(key);
        draw();
      });
    }
    checkbox(box, "map-filter-older",
             "Ältere gespeicherte Meldungen einblenden (" + olderCount + ")",
             state.showOlder, function (ev) {
      state.showOlder = Boolean(ev && ev.target && ev.target.checked);
      draw();
    });
  }

  function draw() {
    const layer = document.getElementById("map-points");
    const note = document.getElementById("map-events-note");
    const box = document.getElementById("map-filters");
    const legend = document.getElementById("map-legend");
    if (!layer || !note) return;
    layer.replaceChildren();

    const byId = new Map();
    for (const s of state.sources) byId.set(s.id, s);

    const points = pointEvents(state.items);
    for (const it of points) drawPoint(layer, it);

    const regions = regionEvents(state.items).map((it) => {
      it.latest = fromLatestFetch(it, byId.get(it.source));
      return it;
    });
    const available = HAZARDS.map((h) => h[0])
      .filter((key) => regions.some((it) => it.metrics && it.metrics.hazard_type === key));
    const olderCount = regions.filter((it) => !it.latest).length;
    // Standard: nur Ereignisse aus dem juengsten erfolgreichen Abruf.
    const shown = regions.filter((it) => (state.showOlder || it.latest) &&
      !state.hidden.has(it.metrics && it.metrics.hazard_type));
    const groups = cluster(shown);
    for (const group of groups) drawRegion(layer, group);

    if (box) renderFilters(box, available, olderCount);

    const lines = [];
    lines.push(points.length ?
      points.length + (points.length === 1 ?
        " Erdbebenposition laut USGS auf der Karte. Marker öffnet die Originalmeldung." :
        " Erdbebenpositionen laut USGS auf der Karte. Marker öffnen die Originalmeldungen.") :
      "Keine punktgenau verorteten Ereignisse in diesem Datenstand. Die leere Karte ist keine Entwarnung.");
    if (regions.length) {
      lines.push(shown.length + " von " + regions.length +
        " GDACS-Meldungen als ungefähre Lage dargestellt, zusammengefasst zu " +
        groups.length + (groups.length === 1 ? " Marker." : " Markern.") +
        (olderCount && !state.showOlder ?
          " " + olderCount + " ältere gespeicherte " +
          (olderCount === 1 ? "Meldung ist" : "Meldungen sind") +
          " ausgeblendet; das ist keine Entwarnung." : ""));
    }
    note.textContent = lines.join(" ");

    if (legend) {
      legend.hidden = !regions.length;
      legend.textContent = regions.length ?
        "Gefüllter Punkt: punktgenaue Koordinate laut USGS. Gestrichelter Ring: ungefähre Lage " +
        "laut GDACS (Zentroid einer Region), keine Schadensfläche. Zahl im Ring: mehrere " +
        "Meldungen, die sich auf der Karte überdecken. Die Farben geben die Warnstufe der " +
        "Quelle wieder (GDACS: Green, Orange, Red) und sind keine eigene Gefahrenbewertung " +
        "von ConflictWatch." : "";
    }
  }

  function render(items, sources) {
    state.items = Array.isArray(items) ? items : [];
    state.sources = Array.isArray(sources) ? sources : [];
    draw();
  }

  window.ConflictWatchMap = {render, project: xy};
})();
