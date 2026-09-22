# ADS-B: aktuelle Flugbeobachtungen (Edge-Option)

Stand 22.09.2026. Die öffentliche GitHub-Pages-Seite veröffentlicht derzeit
**nur einen stündlich neu gebauten, opt-in Flugzeug-Snapshot** aus
`scripts/build_aircraft_snapshot.py`. Das ist kein Live-Tracking.

## Warum der Browser nicht direkt abruft

Der echte HTTP-Test vom GitHub-Actions-Runner mit
`Origin: https://bene901.github.io` auf `https://api.adsb.lol/v2/mil`
lieferte am 22.09.2026 HTTP 200 und JSON, aber **keinen**
`Access-Control-Allow-Origin`-Header. Ein Cross-Origin-`fetch` von GitHub
Pages würde damit im Browser blockiert. Eine bloße Änderung der CSP, ein
öffentlicher CORS-Proxy oder ein eingebauter API-Key löst das nicht belastbar.

Quelle: https://github.com/adsblol/api (dynamische Limits; künftig API-Key
möglich). Daten und API: ODbL 1.0, https://www.adsb.lol/docs/open-data/api/ .

## Minimaler Server-Baustein

`edge/aircraft-worker.mjs` ist ein **optionaler** Cloudflare Worker mit
`GET /v1/aircraft`. Er ruft die Quelle serverseitig ab, gibt nur einen
normalisierten kurzlebigen Beobachtungsbestand zurück und setzt CORS
explizit für `https://bene901.github.io`. Standorte werden nicht zur
ConflictWatch-Ereignisdatenbank hinzugefügt.

- Ersatz-Snapshot im Edge-Cache für 45 Sekunden, kein Flugverlauf.
- Nur Flugzeuge mit von der Quelle gesetztem `dbFlags & 1`, bekannter
  geographischer Position und maximal 120 Sekunden alter Position.
- Quellenantwort älter als fünf Minuten: Fehler und **leerer** Bestand.
- Fehler/429 werden nicht durch einen veralteten Flugzeugbestand ersetzt.
- `license` und `attribution` sind explizit Teil der JSON-Antwort.
- CORS ist ein Browser-Zugriffsschutz, kein Anti-Scraping- oder
  Authentifizierungsmechanismus. Bei öffentlicher Nutzung Cloudflare-Quota
  und adsb.lol-Limits beobachten.

## Vor Freischaltung auf der öffentlichen Seite

1. Einen eigenen Cloudflare-Workers-Zugang verwenden; kostenfreier Tarif
   kann für kleine Tests reichen. Ohne diesen Zugang **kein Live-Endpoint**.
2. Im Cloudflare-Konto eine auf Workers beschränkte API-Berechtigung erstellen
   und die Account-ID ablesen. Beide Werte **nicht in Chat-Nachrichten,
   Dateien oder Quellcode kopieren**. Stattdessen im privaten Repository-Menü
   `Settings → Secrets and variables → Actions` als
   `CLOUDFLARE_API_TOKEN` und `CLOUDFLARE_ACCOUNT_ID` hinterlegen.
3. Auf GitHub unter `Actions → Deploy aircraft edge endpoint → Run workflow`
   die bereitgestellte `workflow_dispatch`-Action starten. Sie verwendet die
   versionierte `edge/wrangler.jsonc`-Konfiguration und installiert Wrangler
   nur in der Actions-Laufzeit; kein lokales Terminal nötig.
4. Die im Deployment ausgegebene Worker-URL mit `/v1/aircraft` prüfen:
   HTTP 200, Header `Access-Control-Allow-Origin`, Schema, Quellzeit und
   Quellenattribution.
5. Erst danach die **konkrete** Worker-URL in die Frontend-Integration
   aufnehmen und die CSP-`connect-src`-Allowlist nur um diesen Host ergänzen.
   Nicht pauschal `*` freigeben. Die stündliche Momentaufnahme bleibt
   unabhängiger Fallback. Bis Schritt 5 ist der Worker **nicht livegeschaltet**.

Cloudflare Workers Free hat laut offizieller Dokumentation derzeit
100.000 Requests/Tag, aber keine garantierte unbegrenzte adsb.lol-Abfragequote.
Eine optionale UI sollte nach Nutzeraktivierung höchstens alle 120 Sekunden
und nur in einem sichtbaren Tab aktualisieren. Kein globales 15-Sekunden-Polling
pro Besucher.

## Interpretation

`/v2/mil` ist eine Klassifikation von empfangenen Luftfahrtsignalen;
sie beweist weder militärische Operationen noch ihre Vollständigkeit.
Quelle, Positionserfassungszeit, mögliche Latenz und Abdeckungsgrenzen
müssen auch später im Interface getrennt von UCDP/GDELT angezeigt werden.
