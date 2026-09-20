# Runbook

## 1. Einmalige Einrichtung

1. Öffentliches GitHub-Repository anlegen, Inhalt dieses Pakets auf `main` pushen.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Settings → Actions → General: Actions erlauben. Workflow-Rechte müssen `contents: write` zulassen (steht im Workflow; eine Organisationsrichtlinie kann das sperren).
4. Den Branch `data-state` NICHT von Hand anlegen. Der erste Lauf erzeugt ihn.
   Der erste Push nach Installation (und spätere Pushs) versucht jetzt einen **echten Quellenabruf**, sofern `min_fetch_interval_h` fällig ist. `schedule` und `workflow_dispatch` nutzen dieselbe Intervallprüfung. Ein grüner Push-Lauf mit `"result":"skipped"` nach einem kurz zuvor erfolgten Abruf ist kein neuer Live-Nachweis.
5. Versionen der verwendeten Actions (`checkout@v4`, `setup-python@v5`, `upload-artifact@v4`, `configure-pages@v5`, `upload-pages-artifact@v3`, `deploy-pages@v4`) beim Anlegen gegen die aktuellen Hauptversionen prüfen.

## 2. Erster GitHub-Lauf: Abnahme in zwei Teilen

### A. Technischer Live-Test (im Repository)

1. Actions → Pipeline → **Run workflow**.
2. Im Log festhalten:
   - „Tests“: alle grün (54 Tests).
   - „Pipeline-Lauf“: `"usgs": {"result": "ok", "items": N, "complete": true}`. **N = 0 ist bestanden**, wenn USGS in dieser Woche kein signifikantes Beben führt.
   - „Bestand sichern“: `State-Revision: <sha>`.
   - „Snapshot und Website bauen“: zwei Zeilen „Snapshot: …“.
   - `deploy`: URL der Seite.
3. Artefakt `nachweis-<run-id>` herunterladen: `raw/usgs_*.json` (echte Rohantwort), `preview/snapshot.json`, `state-repo/state/`.
4. Branch `data-state`: Commit „state: run …“ mit `state/items.json`, `state/sources.json`, `state/runlog.jsonl`.
5. Seite auf dem Handy: „Noch keine Quelle freigegeben …“ (korrekt, solange `public: false`).

**Bestanden, wenn:** Lauf grün; Rohantwort gespeichert; Bestand und beide Snapshots validiert; Seite veröffentlicht. Die Anzahl der Beben spielt keine Rolle.

**Nicht bestanden, wenn:** ein Schritt rot ist. Dann das Log des ersten roten Schritts zurückmelden.

### B. Darstellung eines echten Ereignisses (lokal oder in Claudes Umgebung)

Mit der unveränderten echten Antwort vom 19.09.2026 und deren historischem Zeitpunkt:

```
python -m cw run --state /tmp/dt/state --now 2026-09-19T13:17:00Z \
  --fixture usgs=tests/fixtures/usgs/real_2026-09-19_significant_week.json
python -m cw snapshot --state /tmp/dt/state --now 2026-09-19T13:17:00Z \
  --revision 0000000 --include-unreleased --out /tmp/dt/site/data/snapshot.json
cp site/* /tmp/dt/site/ && python -m http.server -d /tmp/dt/site 8000
```

Die Seite zeigt den echten Eintrag und zugleich den Hinweis „seit mehr als drei Stunden nicht aktualisiert, Letzter Stand: 19.09.2026“. Damit ist der Datensatz ohne zusätzliches UI-Element als historischer Testdatensatz erkennbar. `--now` ist ausschließlich für diesen Test gedacht und wird im Workflow nie verwendet.

### Bekannte, akzeptierte Grenze

Die Aktualität wird beim **Öffnen oder Neuladen** der Seite geprüft. Eine geöffnete Seite aktualisiert weder Daten noch Hinweise; sie ist kein kontinuierlich aktualisiertes Live-Dashboard.

## 3. Live-Tor (7 Tage, Spezifikation C3)

- Stündliche Läufe laufen lassen. `state/runlog.jsonl` auf `data-state` enthält jeden Lauf (14 Tage).
- Mindestens drei Rohantworten verschiedener Tage aus den Artefakten nach `tests/fixtures/usgs/real_<datum>_significant_week.json` übernehmen.
- Stichprobe: bis zu 10 Einträge mit der USGS-Webseite vergleichen (Titel, Zeit, Stufe, Ort).
- Freigabe per Pull Request: `"public": true` in `registry.json`, Protokoll verlinken.

## 4. Betrieb

| Situation | Handlung |
|---|---|
| Workflow rot mit „Alarm“ | Log lesen; Quelle `down` oder alle Abrufe gescheitert |
| Workflow rot bei „Bestand sichern“ | Überlappender Lauf; nächster Lauf korrigiert es |
| Workflow rot bei „Tests“ | Code auf `main` reparieren; bis dahin keine Datenänderung |
| Seite zeigt Hinweis „seit mehr als drei Stunden“ | Actions prüfen; ggf. Workflow reaktivieren |
| Geplanter Workflow deaktiviert (60 Tage) | Actions → Pipeline → Enable workflow, dann Run workflow |
| Fehlerhafter Bestand | Auf `data-state` den letzten guten Commit wiederherstellen (`git revert`), dann Run workflow |
| `data-state` über 100 MB | Branch manuell auf einen Commit zusammenfassen |

## 5. Lokale Vorschau mit echten Daten

```
python -m cw run --state /tmp/st
python -m cw snapshot --state /tmp/st --revision 0000000 --out site/data/snapshot.json --include-unreleased
python -m http.server -d site 8000
```
`site/data/` steht in `.gitignore` und wird nie committet.

## Öffentliche, streng getrennte Testvorschau (keine Quellenfreigabe)

- Die reguläre Adresse `/` erhält **ausschließlich** `_site/data/snapshot.json`, erzeugt ohne `--include-unreleased`. `registry.json` bleibt für USGS und NOAA `public:false` bis zum dokumentierten sieben-Tage-Tor.
- Der deutlich gekennzeichnete Testpfad `/test/` erhält einen **separaten** `_site/test/data/snapshot.json`; dessen Generator `python -m cw.test_preview` erlaubt ausdrücklich **nur** `usgs` und `noaa-swpc`. Er kopiert nicht das uneingeschränkte interne Artefakt `preview/snapshot.json` auf die Website. Neue private Anbieter werden nicht automatisch öffentlich.
- Die Testseite bezeichnet die Werte durchgehend als nicht freigegeben, nennt Zeitstempel, zeigt behördliche Original-Links und erklärt, dass fehlende Meldungen keine Entwarnung sind. Testvorschau ist **öffentlich zugänglich, nicht vertraulich**: nur Quellen-/Ereignisdaten veröffentlichen, deren Nutzungsbedingungen das erlauben. Keine internen Rohantworten, `ingest`-Daten oder Zugangstokens ausgeben.
- Wenn eine Testquelle regulär freigegeben wird, schlägt der bisherige Test-Generator absichtlich fehl: Vor dem nächsten Deploy die doppelte Testansicht separat deaktivieren oder nach erneuter Prüfung ihre Freigabe-Logik anpassen.
- Abnahme: GitHub Actions vollständig grün; Haupt-Snapshot hat bis zur Freigabe 0 Quellen/Einträge, Test-Snapshot enthält nur USGS/NOAA und die echten bekannten Ereignisse/Statuswerte, Testseite hat deutlich sichtbaren Warnhinweis; mobilen Browser und eine fehlerhafte/veraltete Datenantwort gesondert prüfen.
