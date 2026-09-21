"use strict";
// Geographic positions are taken exclusively from source-supplied event coordinates.
// This module NEVER requests the visitor's location or estimates personal distance.
//
// Zwei Ortsgenauigkeiten, zwei Darstellungen:
//   precision "point"  -> USGS-Erdbeben, punktgenaue Koordinate der Quelle.
//   precision "region" -> GDACS-Zentroid einer Region. UNGEFAEHRE Lage, ausdruecklich
//                         keine Schadensflaeche, nie wie ein punktgenauer Ort gezeichnet.
// Warnstufen und Magnituden bleiben Angaben der Quelle. Dieses Modul leitet daraus
// keine eigene Gefahrenbewertung ab und erfindet keine Schwellen.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796;
  const RAD = Math.PI / 180;
  const BASE = {x: 0, y: 0, w: 1000, h: 510};
  const MAX_ZOOM = 64;
  const CLUSTER_PX = 16;   // Bildschirmabstand; beim Hineinzoomen fallen Gruppen auseinander.
  const HAZARDS = [
    ["wildfire", "Waldbrände"],
    ["flood", "Überschwemmungen"],
    ["tropical_cyclone", "Wirbelstürme"],
    ["volcano", "Vulkane"],
    ["drought", "Dürren"],
  ];
  const HAZARD_ONE = {wildfire: "Waldbrand", flood: "Überschwemmung",
                      tropical_cyclone: "Wirbelsturm", volcano: "Vulkan",
                      drought: "Dürre"};
  const LEVEL_ORDER = ["Green", "Orange", "Red"];
  // Der Bestand enthaelt bereits nur Beben ab M4.5 - das ist die Auswahl des
  // USGS-Feeds, nicht unsere. Die Voreinstellung blendet deshalb nichts aus; wer
  // weiter einschraenken will, kann es, und der Hinweistext nennt beides getrennt:
  // was die Quelle gar nicht liefert und was gerade ausgeblendet ist.
  const MAGNITUDES = [
    [0, "alle gespeicherten"],
    [5, "ab Magnitude 5"],
    [6, "ab Magnitude 6"],
    [7, "ab Magnitude 7"],
  ];
  const SOURCE_FLOOR = "Abgedeckt sind Beben ab Magnitude 4,5 laut USGS; schwächere Beben " +
    "liefert die Quelle nicht und das ist keine Entwarnung.";
  const WINDOWS = [
    [24, "letzte 24 Stunden"],
    [168, "letzte 7 Tage"],
    [0, "gesamter Datenstand"],
  ];

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

  const state = {
    hidden: new Set(), showOlder: false, minMag: 0, windowH: 24,
    items: [], sources: [], view: Object.assign({}, BASE),
    selectedId: null, onSelect: null,
  };

  const zoom = () => BASE.w / state.view.w;
  // Marker sollen beim Zoomen ihre Bildschirmgroesse behalten, nicht mitwachsen.
  const px = (v) => v / zoom();

  function clampView(v) {
    const w = Math.min(BASE.w, Math.max(BASE.w / MAX_ZOOM, v.w));
    const h = w * BASE.h / BASE.w;
    return {
      w: w, h: h,
      x: Math.min(BASE.w - w, Math.max(0, v.x)),
      y: Math.min(BASE.h - h, Math.max(0, v.y)),
    };
  }

  function zoomBy(factor, cx, cy) {
    const v = state.view;
    const fx = typeof cx === "number" ? cx : v.x + v.w / 2;
    const fy = typeof cy === "number" ? cy : v.y + v.h / 2;
    const w = v.w / factor;
    const h = w * BASE.h / BASE.w;
    state.view = clampView({w: w, h: h,
                            x: fx - (fx - v.x) * (w / v.w),
                            y: fy - (fy - v.y) * (h / v.h)});
    draw();
  }

  function panBy(dx, dy) {
    state.view = clampView({w: state.view.w, h: state.view.h,
                            x: state.view.x + dx, y: state.view.y + dy});
    draw();
  }

  function resetView() {
    state.view = Object.assign({}, BASE);
    draw();
  }

  // "Aus dem juengsten erfolgreichen Abruf" - dieselbe Regel wie in der Liste.
  // Sie sagt nur: die Quelle meldet den Eintrag weiterhin. Kein Beleg fuer Fortdauer.
  function fromLatestFetch(it, src) {
    return Boolean(src && src.last_success_at && it.last_seen_at === src.last_success_at);
  }

  function locatable(it) {
    return it.kind === "event" && it.location && xy(it.location.lon, it.location.lat);
  }

  function pointEvents(items) {
    return items.filter((it) => locatable(it) && it.location.precision === "point");
  }

  function regionEvents(items) {
    return items.filter((it) => locatable(it) && it.location.precision === "region");
  }

  const magnitudeOf = (it) => (it.metrics && typeof it.metrics.magnitude === "number")
    ? it.metrics.magnitude : null;

  const displayTime = (it) => Date.parse(it.kind === "event" ? it.occurred_at :
    it.kind === "report" ? it.published_at : it.observed_at);

  // Bezugszeit ist der juengste erfolgreiche Abruf im Datenstand, nicht die Uhr des
  // Besuchers: "letzte 24 Stunden" bezieht sich damit auf die Daten, nicht auf jetzt.
  function referenceTime(sources) {
    const times = sources.map((s) => Date.parse(s.last_success_at))
      .filter((t) => Number.isFinite(t));
    return times.length ? Math.max.apply(null, times) : NaN;
  }

  // Der Zeitfilter folgt derselben Unterscheidung wie die Meldungsliste: bei
  // Zeitpunkt-Quellen (USGS) zaehlt die Anzeigezeit des Ereignisses, bei Dauer-Quellen
  // (GDACS) die letzte Sichtung. Sonst faellt ein seit Monaten brennender Waldbrand
  // aus "letzte 24 Stunden" heraus, obwohl die Quelle ihn heute noch meldet.
  function windowTime(it, src) {
    if (src && src.highlight && src.highlight.recency_basis === "last_seen") {
      return Date.parse(it.last_seen_at);
    }
    return displayTime(it);
  }

  function withinWindow(it, src, ref) {
    if (!state.windowH || !Number.isFinite(ref)) return true;
    const t = windowTime(it, src);
    return !Number.isFinite(t) || (ref - t) <= state.windowH * 3600 * 1000;
  }

  function markerAction(label, onActivate, selected) {
    const a = svg("a");
    a.setAttribute("role", "button");
    a.setAttribute("tabindex", "0");
    a.setAttribute("aria-label", label);
    if (selected) a.setAttribute("aria-pressed", "true");
    function activate(ev) {
      if (ev && ev.preventDefault) ev.preventDefault();
      if (ev && ev.stopPropagation) ev.stopPropagation();
      onActivate();
    }
    a.addEventListener("click", activate);
    a.addEventListener("keydown", function (ev) {
      if (!ev || (ev.key !== "Enter" && ev.key !== " ")) return;
      activate(ev);
    });
    return a;
  }

  function selectItem(it) {
    state.selectedId = it.id || null;
    draw();
    if (state.onSelect) state.onSelect(it);
  }

  function circle(pos, r, cls) {
    const c = svg("circle");
    c.setAttribute("cx", pos[0].toFixed(2));
    c.setAttribute("cy", pos[1].toFixed(2));
    c.setAttribute("r", r.toFixed(2));
    if (cls) c.setAttribute("class", cls);
    else c.setAttribute("fill", "transparent");
    return c;
  }

  // Gruppiert nur Marker mit gleichem Schluessel, die einander auf dem Bildschirm
  // ueberdecken. Punktgenaue und ungefaehre Orte werden nie zusammengefasst.
  function cluster(events, keyOf) {
    const groups = [];
    const reach = px(CLUSTER_PX);
    for (const it of events) {
      const pos = xy(it.location.lon, it.location.lat);
      const key = keyOf(it);
      const near = groups.find((g) => g.key === key &&
        Math.hypot(g.pos[0] - pos[0], g.pos[1] - pos[1]) <= reach);
      if (near) near.items.push(it);
      else groups.push({key: key, pos: pos, items: [it]});
    }
    return groups;
  }

  function countLabel(a, pos, n) {
    const t = svg("text");
    t.setAttribute("x", pos[0].toFixed(2));
    t.setAttribute("y", (pos[1] + px(4)).toFixed(2));
    t.setAttribute("class", "map-cluster-count");
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("font-size", px(11).toFixed(2));
    t.textContent = String(n);
    a.append(t);
  }

  function drawQuakes(layer, group) {
    const pos = group.pos;
    const many = group.items.length > 1;
    const mags = group.items.map(magnitudeOf).filter((m) => m !== null);
    const strongest = mags.length ? Math.max.apply(null, mags) : null;
    const parts = [];
    if (many) {
      parts.push(group.items.length + " Erdbeben laut USGS, hier zusammengefasst, weil sich die Marker überdecken");
      if (strongest !== null) parts.push("stärkstes laut Quelle Magnitude " + strongest.toFixed(1));
      parts.push("zum Auseinanderziehen in die Karte hineinzoomen");
    } else {
      const it = group.items[0];
      parts.push(it.title);
      parts.push("Quelle: " + it.source);
      parts.push("Ort: " + (it.location.name || "geografische Position laut Quelle"));
      const felt = it.metrics && it.metrics.felt_reports;
      if (typeof felt === "number") {
        parts.push(felt + (felt === 1 ? " Rückmeldung" : " Rückmeldungen") + " von Menschen");
      }
    }
    const label = parts.join(". ") + ".";
    const selected = !many && group.items[0].id === state.selectedId;
    const a = markerAction(
      label + (many ? " Auswählen, um hineinzuzoomen." : " Details auf ConflictWatch anzeigen."),
      many ? () => zoomBy(1.8, pos[0], pos[1]) : () => selectItem(group.items[0]),
      selected
    );
    a.append(circle(pos, px(19), null),
             circle(pos, px(many ? 11 : 8),
                    "map-event-point" + (many ? " is-cluster" : "") + (selected ? " is-selected" : "")));
    if (many) countLabel(a, pos, group.items.length);
    const title = svg("title");
    title.textContent = label;
    a.append(title);
    layer.append(a);
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
    const plural = (HAZARDS.find((h) => h[0] === group.key) || [null, "Ereignisse"])[1];
    const singular = HAZARD_ONE[group.key] || "Ereignis";
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
    const selected = !many && group.items[0].id === state.selectedId;
    const a = markerAction(
      label + (many ? " Auswählen, um hineinzuzoomen." : " Details auf ConflictWatch anzeigen."),
      many ? () => zoomBy(1.8, pos[0], pos[1]) : () => selectItem(group.items[0]),
      selected
    );
    const marker = circle(pos, px(many ? 13 : 10),
      "map-event-region" + (many ? " is-cluster" : "") +
      (group.items.every((it) => !it.latest) ? " is-older" : "") +
      (selected ? " is-selected" : ""));
    if (level.top) marker.setAttribute("data-level", level.top.toLowerCase());
    a.append(circle(pos, px(19), null), marker);
    if (many) countLabel(a, pos, group.items.length);
    const title = svg("title");
    title.textContent = label;
    a.append(title);
    layer.append(a);
  }

  function control(box, tag, attrs, text, onChange) {
    const el = document.createElement(tag);
    for (const k in attrs) el[k] = attrs[k];
    if (text !== undefined) el.textContent = text;
    if (onChange) el.addEventListener(tag === "button" ? "click" : "change", onChange);
    box.append(el);
    return el;
  }

  function labelled(box, id, text) {
    const wrap = document.createElement("label");
    wrap.className = "map-filter";
    wrap.htmlFor = id;
    wrap.textContent = text;
    box.append(wrap);
    return wrap;
  }

  function select(box, id, labelText, options, current, onPick) {
    labelled(box, id, labelText);
    const sel = document.createElement("select");
    sel.id = id;
    sel.className = "map-select";
    for (const [value, text] of options) {
      const opt = document.createElement("option");
      opt.value = String(value);
      opt.textContent = text;
      opt.selected = value === current;
      sel.append(opt);
    }
    sel.value = String(current);
    sel.addEventListener("change", function (ev) {
      onPick(Number(ev && ev.target ? ev.target.value : current));
      draw();
    });
    box.append(sel);
    return sel;
  }

  function checkbox(box, id, labelText, checked, onChange) {
    const wrap = document.createElement("label");
    wrap.className = "map-filter";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    input.checked = checked;
    input.addEventListener("change", onChange);
    const span = document.createElement("span");
    span.textContent = labelText;
    wrap.append(input, span);
    box.append(wrap);
    return input;
  }

  function renderControls(box, hasQuakes, available, olderCount) {
    box.replaceChildren();
    box.hidden = !hasQuakes && !available.length;
    if (box.hidden) return;

    if (hasQuakes) {
      select(box, "map-filter-magnitude", "Magnitude:", MAGNITUDES, state.minMag,
             (v) => { state.minMag = v; });
    }
    select(box, "map-filter-window", "Zeitraum:", WINDOWS, state.windowH,
           (v) => { state.windowH = v; });
    for (const [key, labelText] of HAZARDS) {
      if (!available.includes(key)) continue;
      checkbox(box, "map-filter-" + key.replace(/_/g, "-"), labelText,
               !state.hidden.has(key), function (ev) {
        if (ev && ev.target && ev.target.checked === false) state.hidden.add(key);
        else state.hidden.delete(key);
        draw();
      });
    }
    if (available.length) {
      checkbox(box, "map-filter-older",
               "Ältere gespeicherte Meldungen einblenden (" + olderCount + ")",
               state.showOlder, function (ev) {
        state.showOlder = Boolean(ev && ev.target && ev.target.checked);
        draw();
      });
    }
    control(box, "button", {id: "map-zoom-in", type: "button", className: "map-btn"},
            "Vergrößern", () => zoomBy(1.6));
    control(box, "button", {id: "map-zoom-out", type: "button", className: "map-btn"},
            "Verkleinern", () => zoomBy(1 / 1.6));
    control(box, "button", {id: "map-zoom-reset", type: "button", className: "map-btn"},
            "Ganze Welt", resetView);
  }

  function noteText(shownQuakes, allQuakes, quakeGroups, shownRegions, allRegions,
                    regionGroups, olderCount) {
    const parts = [];
    if (allQuakes) parts.push(shownQuakes + " Erdbeben (USGS)");
    if (allRegions) parts.push(shownRegions + " Naturereignisse (GDACS)");
    if (!parts.length) parts.push("Keine verorteten Meldungen – keine Entwarnung");
    if (olderCount && !state.showOlder) {
      parts.push(olderCount + " ältere Meldungen ausgeblendet – keine Entwarnung");
    }
    return parts.join(" · ");
  }

  function draw() {
    const view = document.getElementById("map-view");
    const layer = document.getElementById("map-points");
    const note = document.getElementById("map-events-note");
    const box = document.getElementById("map-filters");
    const legend = document.getElementById("map-legend");
    if (!layer || !note) return;
    layer.replaceChildren();
    if (view) {
      const v = state.view;
      view.setAttribute("viewBox", [v.x, v.y, v.w, v.h].map((n) => n.toFixed(2)).join(" "));
    }

    const byId = new Map();
    for (const s of state.sources) byId.set(s.id, s);
    const ref = referenceTime(state.sources);

    const quakes = pointEvents(state.items);
    const shownQuakes = quakes.filter((it) => {
      const m = magnitudeOf(it);
      // Ein Ereignis ohne Magnitude wird von einem Magnitudenfilter nicht erfasst.
      return (m === null || m >= state.minMag) && withinWindow(it, byId.get(it.source), ref);
    });
    const quakeGroups = cluster(shownQuakes, () => "point");
    for (const g of quakeGroups) drawQuakes(layer, g);

    const regions = regionEvents(state.items).map((it) => {
      it.latest = fromLatestFetch(it, byId.get(it.source));
      return it;
    });
    const available = HAZARDS.map((h) => h[0])
      .filter((key) => regions.some((it) => it.metrics && it.metrics.hazard_type === key));
    const olderCount = regions.filter((it) => !it.latest).length;
    const shownRegions = regions.filter((it) => (state.showOlder || it.latest) &&
      !state.hidden.has(it.metrics && it.metrics.hazard_type) &&
      withinWindow(it, byId.get(it.source), ref));
    const regionGroups = cluster(shownRegions, (it) => it.metrics && it.metrics.hazard_type);
    for (const g of regionGroups) drawRegion(layer, g);

    if (box) renderControls(box, quakes.length > 0, available, olderCount);
    note.textContent = noteText(shownQuakes.length, quakes.length, quakeGroups.length,
                                shownRegions.length, regions.length, regionGroups.length,
                                olderCount);

    if (legend) {
      const parts = [];
      if (quakes.length) parts.push("● Erdbeben laut USGS (ab M 4,5)");
      if (regions.length) parts.push("◌ GDACS: ungefähre Lage, keine Schadensfläche");
      if (parts.length) parts.push("Zahl = Gruppe · Warnstufen laut Quelle, keine eigene Gefahrenbewertung");
      legend.hidden = !parts.length;
      legend.textContent = parts.join(" · ");
    }
  }

  function clientToMap(view, clientX, clientY) {
    const rect = view && view.getBoundingClientRect ? view.getBoundingClientRect() : null;
    if (!rect || !rect.width || !rect.height) {
      return [state.view.x + state.view.w / 2, state.view.y + state.view.h / 2];
    }
    return [
      state.view.x + ((clientX - rect.left) / rect.width) * state.view.w,
      state.view.y + ((clientY - rect.top) / rect.height) * state.view.h,
    ];
  }

  function zoomAtClient(view, factor, clientX, clientY) {
    const focus = clientToMap(view, clientX, clientY);
    zoomBy(factor, focus[0], focus[1]);
  }

  // Kombiniert Verschieben und Skalieren in EINEM ViewBox-Schritt. Der Kartenpunkt,
  // der vorher unter oldClient lag, bleibt nach der Geste unter newClient. So fuehlt
  // sich Pinch-Zoom wie eine echte Karte an statt wie ein Zoom um die Bildmitte.
  function gestureView(view, factor, oldClient, newClient) {
    const rect = view && view.getBoundingClientRect ? view.getBoundingClientRect() : null;
    if (!rect || !rect.width || !rect.height || !Number.isFinite(factor) || factor <= 0) return;
    const v = state.view;
    const focusX = v.x + ((oldClient.x - rect.left) / rect.width) * v.w;
    const focusY = v.y + ((oldClient.y - rect.top) / rect.height) * v.h;
    const w = v.w / factor;
    const h = w * BASE.h / BASE.w;
    const rx = (newClient.x - rect.left) / rect.width;
    const ry = (newClient.y - rect.top) / rect.height;
    state.view = clampView({w: w, h: h, x: focusX - rx * w, y: focusY - ry * h});
    draw();
  }

  function wireNavigation(view) {
    if (!view || !view.addEventListener || view.dataset.navReady === "1") return;
    view.dataset.navReady = "1";
    view.setAttribute("tabindex", "0");

    // Maus/Trackpad: am Zeiger zoomen, nicht starr um die Kartenmitte.
    view.addEventListener("wheel", function (ev) {
      if (ev.preventDefault) ev.preventDefault();
      const raw = Math.exp(-Number(ev.deltaY || 0) * 0.0018);
      const factor = Math.max(0.72, Math.min(1.38, raw));
      zoomAtClient(view, factor, Number(ev.clientX || 0), Number(ev.clientY || 0));
    }, {passive: false});

    view.addEventListener("dblclick", function (ev) {
      if (ev.preventDefault) ev.preventDefault();
      zoomAtClient(view, 1.8, Number(ev.clientX || 0), Number(ev.clientY || 0));
    });

    const pointers = new Map();
    let drag = null;
    let pinch = null;
    let lastTap = null;

    function isMarkerTarget(ev) {
      return Boolean(ev && ev.target && ev.target.closest &&
        ev.target.closest("#map-points a"));
    }

    function pair() {
      return Array.from(pointers.values()).slice(0, 2);
    }

    function midpoint(a, b) {
      return {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
    }

    function distance(a, b) {
      return Math.hypot(a.x - b.x, a.y - b.y);
    }

    function beginPinch() {
      const ps = pair();
      if (ps.length < 2) { pinch = null; return; }
      pinch = {distance: Math.max(1, distance(ps[0], ps[1])), mid: midpoint(ps[0], ps[1])};
      drag = null;
    }

    view.addEventListener("pointerdown", function (ev) {
      if (ev.pointerType === "mouse" && ev.button !== undefined && ev.button !== 0) return;
      const id = ev.pointerId === undefined ? 1 : ev.pointerId;
      const p = {id: id, x: ev.clientX, y: ev.clientY, marker: isMarkerTarget(ev)};
      pointers.set(id, p);
      if (view.setPointerCapture && ev.pointerId !== undefined) {
        try { view.setPointerCapture(ev.pointerId); } catch (_) {}
      }
      if (pointers.size >= 2) beginPinch();
      else drag = {
        id: id, x: p.x, y: p.y, startX: p.x, startY: p.y,
        moved: false, marker: p.marker, pointerType: ev.pointerType || "",
        startedAt: Number(ev.timeStamp || 0),
      };
    });

    view.addEventListener("pointermove", function (ev) {
      const id = ev.pointerId === undefined ? 1 : ev.pointerId;
      if (!pointers.has(id)) return;
      pointers.set(id, {id: id, x: ev.clientX, y: ev.clientY,
                        marker: pointers.get(id).marker});

      if (pointers.size >= 2) {
        if (ev.preventDefault) ev.preventDefault();
        const ps = pair();
        const nextDistance = Math.max(1, distance(ps[0], ps[1]));
        const nextMid = midpoint(ps[0], ps[1]);
        if (!pinch) beginPinch();
        if (pinch) {
          gestureView(view, nextDistance / pinch.distance, pinch.mid, nextMid);
          pinch = {distance: nextDistance, mid: nextMid};
        }
        return;
      }

      if (!drag || drag.id !== id) return;
      const dx = drag.x - ev.clientX;
      const dy = drag.y - ev.clientY;
      if (Math.hypot(ev.clientX - drag.startX, ev.clientY - drag.startY) > 4) {
        drag.moved = true;
      }
      const rect = view.getBoundingClientRect ? view.getBoundingClientRect() : null;
      const sx = rect && rect.width ? state.view.w / rect.width : 1;
      const sy = rect && rect.height ? state.view.h / rect.height : sx;
      panBy(dx * sx, dy * sy);
      drag.x = ev.clientX;
      drag.y = ev.clientY;
    });

    function finishPointer(ev) {
      const id = ev.pointerId === undefined ? 1 : ev.pointerId;
      const finishedDrag = drag && drag.id === id ? drag : null;
      pointers.delete(id);
      if (view.releasePointerCapture && ev.pointerId !== undefined) {
        try { view.releasePointerCapture(ev.pointerId); } catch (_) {}
      }

      if (pointers.size >= 2) {
        beginPinch();
        return;
      }
      pinch = null;

      if (pointers.size === 1) {
        const p = Array.from(pointers.values())[0];
        drag = {id: p.id, x: p.x, y: p.y, startX: p.x, startY: p.y,
                moved: true, marker: p.marker, pointerType: ev.pointerType || "",
                startedAt: Number(ev.timeStamp || 0)};
        return;
      }

      drag = null;
      if (!finishedDrag || finishedDrag.moved || finishedDrag.marker ||
          finishedDrag.pointerType !== "touch") return;

      // Doppeltipp: schneller Zoom um die angetippte Stelle.
      const t = Number(ev.timeStamp || 0);
      const tap = {time: t, x: ev.clientX, y: ev.clientY};
      if (lastTap && t - lastTap.time > 0 && t - lastTap.time < 350 &&
          Math.hypot(tap.x - lastTap.x, tap.y - lastTap.y) < 30) {
        zoomAtClient(view, 1.8, tap.x, tap.y);
        lastTap = null;
      } else {
        lastTap = tap;
      }
    }

    for (const type of ["pointerup", "pointercancel", "pointerleave"]) {
      view.addEventListener(type, finishPointer);
    }

    view.addEventListener("keydown", function (ev) {
      const step = state.view.w / 8;
      const keys = {ArrowLeft: [-step, 0], ArrowRight: [step, 0],
                    ArrowUp: [0, -step], ArrowDown: [0, step]};
      if (keys[ev.key]) { panBy(keys[ev.key][0], keys[ev.key][1]); }
      else if (ev.key === "+") zoomBy(1.6);
      else if (ev.key === "-") zoomBy(1 / 1.6);
      else if (ev.key === "0") resetView();
      else return;
      if (ev.preventDefault) ev.preventDefault();
    });
  }

  function render(items, sources, onSelect) {
    state.items = Array.isArray(items) ? items : [];
    state.sources = Array.isArray(sources) ? sources : [];
    state.onSelect = typeof onSelect === "function" ? onSelect : null;
    state.selectedId = null;
    state.view = Object.assign({}, BASE);
    wireNavigation(document.getElementById("map-view"));
    draw();
  }

  // zoomBy/panBy/resetView sind dieselben Einstiege, die auch die Bedienelemente
  // benutzen; sie sind freigelegt, damit die Navigation pruefbar ist.
  window.ConflictWatchMap = {render, project: xy, zoomBy, panBy, resetView,
                             viewBox: () => Object.assign({}, state.view)};
})();
