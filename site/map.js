"use strict";
// Geographic positions are taken exclusively from source-supplied event coordinates.
// This module NEVER requests the visitor's location or estimates personal distance.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796;
  const RAD = Math.PI / 180;

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

  function render(items) {
    const svgRoot = document.getElementById("map-view");
    const layer = document.getElementById("map-points");
    const note = document.getElementById("map-events-note");
    if (!svgRoot || !layer || !note) return;
    layer.replaceChildren();
    // The map is only for point-precision source events; global NOAA status is not geolocatable.
    const events = items.filter((it) => it.kind === "event" &&
      it.location && it.location.precision === "point" &&
      xy(it.location.lon, it.location.lat));
    for (const it of events) {
      const pos = xy(it.location.lon, it.location.lat);
      const label = it.title + ". Quelle: " + it.source +
        ". Ort: " + (it.location.name || "geografische Position laut Quelle");
      const link = svg("a");
      if (typeof it.url === "string" && /^https:\/\//.test(it.url)) {
        link.setAttribute("href", it.url);
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      }
      link.setAttribute("aria-label", label + ". Originalmeldung öffnen");
      const hit = svg("circle");
      hit.setAttribute("cx", pos[0].toFixed(2));
      hit.setAttribute("cy", pos[1].toFixed(2));
      hit.setAttribute("r", "19");
      hit.setAttribute("fill", "transparent");
      const marker = svg("circle");
      marker.setAttribute("cx", pos[0].toFixed(2));
      marker.setAttribute("cy", pos[1].toFixed(2));
      marker.setAttribute("r", "8");
      marker.setAttribute("class", "map-event-point");
      const title = svg("title");
      title.textContent = label;
      link.append(hit, marker, title);
      layer.append(link);
    }
    note.textContent = events.length ?
      events.length + (events.length === 1 ?
        " Erdbebenposition laut USGS auf der Karte. Marker öffnet die Originalmeldung." :
        " Erdbebenpositionen laut USGS auf der Karte. Marker öffnen die Originalmeldungen.") :
      "Keine punktgenau verorteten Ereignisse in diesem Datenstand. Die leere Karte ist keine Entwarnung.";
  }
  window.ConflictWatchMap = { render, project: xy };
})();
