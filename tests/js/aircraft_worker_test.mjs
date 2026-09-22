import assert from "node:assert/strict";
import worker, {normalize} from "../../edge/aircraft-worker.mjs";

const now = Date.parse("2026-09-22T21:50:00Z");
const plane = (id = "abc123", patch = {}) => ({
  hex: id, dbFlags: 1, lat: 52.5, lon: 13.4, seen_pos: 2,
  flight: "TEST  ", t: "C30J", gs: 240, alt_baro: 12000, ...patch,
});
const data = (rows) => ({now, ac: rows});

const doc = normalize(data([
  plane(), plane("abc123", {lon: 20}), plane("abc124", {seen_pos:180}),
  plane("abc125", {dbFlags:0}), plane("abc126",{lat:100}), plane("abc127",{gs:NaN}),
]), now);
assert.equal(doc.status, "ok");
assert.deepEqual(doc.aircraft.map(x=>x.id), ["abc123","abc127"]);
assert.equal(doc.aircraft[0].position_time, "2026-09-22T21:49:58Z");
assert.equal(doc.aircraft[0].lat, 52.5);
assert.equal(doc.aircraft[0].speed_kt, 240);
assert.ok(!("speed_kt" in doc.aircraft[1]));
assert.ok(doc.license.endsWith("/odbl/1-0/"));
assert.throws(()=>normalize(data([plane()]),now + 301000), /outdated_source_response/);
assert.throws(()=>normalize({now,ac:null},now), /invalid_schema/);
assert.equal(normalize(data([plane("abc124",{seen_pos:200})]),now).status,"empty");

const saved = new Map();
globalThis.caches = {default:{
  async match(request){return saved.get(request.url)?.clone() || undefined;},
  async put(request,response){saved.set(request.url,response.clone());},
}};
let upstreamCalls = 0;
globalThis.fetch = async (url)=>{
  assert.equal(url,"https://api.adsb.lol/v2/mil");
  upstreamCalls += 1;
  return new Response(JSON.stringify(data([plane()])),{status:200});
};
const waits=[];
const ctx={waitUntil(p){waits.push(p);}};
const env={ALLOWED_ORIGIN:"https://bene901.github.io"};
const request=(origin="https://bene901.github.io",method="GET",path="/v1/aircraft")=>
  new Request("https://example.workers.dev"+path,{method,headers:{"Origin":origin}});
const denied=await worker.fetch(request("https://another.example"),env,ctx);
assert.equal(denied.status,403);
assert.equal(denied.headers.get("Access-Control-Allow-Origin"),null);
assert.equal(upstreamCalls,0);
const wrong=await worker.fetch(request(undefined,"GET","/anything"),env,ctx);
assert.equal(wrong.status,404);
const preflight=await worker.fetch(request(undefined,"OPTIONS"),env,ctx);
assert.equal(preflight.status,204);
assert.equal(preflight.headers.get("Access-Control-Allow-Origin"),env.ALLOWED_ORIGIN);

const first=await worker.fetch(request(),env,ctx);
assert.equal(first.status,200);
assert.equal(first.headers.get("Access-Control-Allow-Origin"),env.ALLOWED_ORIGIN);
assert.equal((await first.json()).aircraft.length,1);
await Promise.all(waits);
const second=await worker.fetch(request(),env,ctx);
assert.equal(second.status,200);
assert.equal(upstreamCalls,1,"cached snapshot must avoid repeated upstream calls");

saved.clear();
globalThis.fetch=async()=>new Response("rate limited",{status:429});
const failed=await worker.fetch(request(),env,ctx);
assert.equal(failed.status,503);
assert.equal((await failed.json()).aircraft.length,0);
assert.equal(failed.headers.get("Cache-Control"),"no-store");

console.log("ADS-B Worker normalization, CORS, cache and fail-closed tests: OK");
