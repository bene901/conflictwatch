// Optional Cloudflare Worker for current ADS-B observations.
// Separate from ConflictWatch's historical event database and hourly Pages snapshot.
// Public source: https://api.adsb.lol/v2/mil (ODbL 1.0).
const UPSTREAM = "https://api.adsb.lol/v2/mil";
const LICENSE = "https://opendatacommons.org/licenses/odbl/1-0/";
const MAX_POSITION_AGE_S = 120;
const MAX_RESPONSE_AGE_S = 300;
const MAX_AIRCRAFT = 2000;
const CACHE_SECONDS = 45;

const numeric = (x, low, high) =>
  typeof x === "number" && Number.isFinite(x) && x >= low && x <= high ? x : null;
const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

export function normalize(payload, fetchedAtMs) {
  if (!payload || !Array.isArray(payload.ac)) throw Error("invalid_schema");
  const epoch = numeric(payload.now, 0, 4102444800000);
  if (epoch === null) throw Error("missing_source_time");
  // The source's 'now' is Unix milliseconds; neither 'seen_pos' nor the
  // time of the HTTP response is the timestamp of an aircraft observation.
  if (Math.abs(fetchedAtMs - epoch) > MAX_RESPONSE_AGE_S * 1000)
    throw Error("outdated_source_response");

  const records = [];
  const seen = new Set();
  for (const a of payload.ac) {
    if (!a || typeof a !== "object" ||
        typeof a.hex !== "string" || !/^[0-9a-f]{6}$/i.test(a.hex)) continue;
    const id = a.hex.toLowerCase();
    if (seen.has(id)) continue;
    seen.add(id);
    if (!Number.isInteger(a.dbFlags) || !(a.dbFlags & 1)) continue;
    const lat = numeric(a.lat, -90, 90);
    const lon = numeric(a.lon, -180, 180);
    const age = numeric(a.seen_pos, 0, MAX_POSITION_AGE_S);
    if (lat === null || lon === null || age === null) continue;
    records.push({
      id,
      lat: Math.round(lat * 1000) / 1000,
      lon: Math.round(lon * 1000) / 1000,
      position_time: iso(epoch - age * 1000),
      callsign: typeof a.flight === "string" ? a.flight.trim().slice(0, 16) : "",
      aircraft_type: typeof a.t === "string" ? a.t.trim().slice(0, 12) : "",
      ...(numeric(a.alt_baro, -2000, 100000) !== null
        ? {altitude_ft: Math.round(a.alt_baro)} : {}),
      ...(numeric(a.gs, 0, 2000) !== null
        ? {speed_kt: Math.round(a.gs)} : {}),
    });
    if (records.length > MAX_AIRCRAFT) throw Error("aircraft_limit_exceeded");
  }
  return {
    schema_version: 1,
    status: records.length ? "ok" : "empty",
    fetched_at: iso(fetchedAtMs),
    observed_at: iso(epoch),
    source: "adsb.lol /v2/mil",
    attribution: "© adsb.lol contributors · ODbL 1.0",
    license: LICENSE,
    coverage_note: "Empfangene, von adsb.lol als militärisch markierte ADS-B/MLAT-Beobachtungen. Nicht vollständig; kein Nachweis eines militärischen Einsatzes.",
    aircraft: records,
  };
}

function json(body, status, origin, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": origin,
      "Vary": "Origin",
      "Cache-Control": status === 200
        ? "public, max-age=45, s-maxage=45" : "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extra,
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    const origin = env.ALLOWED_ORIGIN || "https://bene901.github.io";
    const requestedOrigin = request.headers.get("Origin");
    const url = new URL(request.url);
    if (url.pathname !== "/v1/aircraft" || (request.method !== "GET" && request.method !== "OPTIONS"))
      return new Response("Not found", {status:404});
    if (requestedOrigin && requestedOrigin !== origin)
      return new Response("Forbidden", {status:403});
    if (request.method === "OPTIONS")
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin,
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "3600",
          "Vary": "Origin",
        },
      });

    // No user data or history is stored. Cache only a short, shared replacement
    // snapshot; the upstream is never fetched more often than a cache miss per PoP.
    const cache = caches.default;
    const key = new Request(url.origin + "/v1/aircraft", {method:"GET"});
    const cached = await cache.match(key);
    if (cached) return cached;

    try {
      const upstream = await fetch(UPSTREAM, {signal: AbortSignal.timeout(8500)});
      if (!upstream.ok) throw Error("upstream_http_" + upstream.status);
      const payload = await upstream.json();
      const doc = normalize(payload, Date.now());
      const response = json(doc, 200, origin);
      ctx.waitUntil(cache.put(key, response.clone()));
      return response;
    } catch (err) {
      return json({
        schema_version: 1, status: "unavailable", aircraft: [],
        source: "adsb.lol /v2/mil",
        error_code: typeof err.message === "string" ? err.message.slice(0, 60) : "upstream_error",
      }, 503, origin);
    }
  },
};
