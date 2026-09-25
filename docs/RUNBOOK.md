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
   - „Tests“: vollständige Testsuite grün (aktuell 131 Tests).
   - „Pipeline-Lauf“: `"usgs": {"result": "ok", "items": N, "complete": true}`. **N = 0 ist technisch zulässig**, wenn der USGS-Feed in den letzten 24 Stunden kein Beben ab M4,5 liefert.
   - „Bestand sichern“: `State-Revision: <sha>`.
   - „Snapshot und Website bauen“: zwei Zeilen „Snapshot: …“.
   - `deploy`: URL der Seite.
3. Artefakt `nachweis-<run-id>` herunterladen: `raw/usgs_*.json` (echte Rohantwort), `preview/snapshot.json`, `state-repo/state/`.
4. Branch `data-state`: Commit „state: run …“ mit `state/items.json`, `state/sources.json`, `state/runlog.jsonl`.
5. Seite auf dem Handy: Meldungen aller drei Quellen sichtbar (alle `public: true`).

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

## 3. Betriebsbeobachtung nach Freigabe

Die frühere 7-Tage-Vorabbedingung ist für diesen Release aufgehoben. Die Beobachtung bleibt trotzdem Teil des Betriebs und ist **kein Freigabeschalter** mehr.

- Stündliche Läufe weiterlaufen lassen. `state/runlog.jsonl` auf `data-state` enthält jeden Lauf (14 Tage).
- Rohantworten verschiedener Tage als Evidenz sichern; neue dauerhafte Fixtures nur anlegen, wenn sie einen zusätzlichen Parser-/Regressionsfall belegen.
- Stichprobenartig USGS-Einträge mit der Originalquelle vergleichen (Zeit, Magnitude, Ort, PAGER sowie vorhandene MMI/CDI/Felt-Werte).
- GDACS auf Episodenwechsel und 30-Tage-Expiry beobachten; zusätzlich die getrennten VO-/DR-Feeds prüfen (VO darf legitimerweise leer sein, DR hat einen 72-h-Leerwächter). NOAA auf Aktualität der beobachteten G/S/R-Werte prüfen.
- Bei fachlicher oder technischer Regression Quelle nicht stillschweigend als korrekt darstellen: Fehlerstatus sichtbar halten und Ursache im Issue/PR dokumentieren.

## 4. Betrieb

| Situation | Handlung |
|---|---|
| Workflow rot mit „Alarm“ | `alarm.json` im Schritt „Alarm auswerten“ lesen: `newly_down` = Quelle neu ausgefallen; `all_failed` = alle versuchten Abrufe gescheitert; `recovered_fetch_gaps` = eine veröffentlichte Quelle wurde erst nach Überschreitung ihrer `max_fetch_gap_h`-Grenze erfolgreich erneut abgerufen. Ein solcher Lauf kann nach erfolgreichem State-Push und Pages-Deploy rot sein, obwohl die Quelle wieder `fetch_health: ok` meldet. |
| Workflow rot bei „Bestand sichern“ | Überlappender Lauf; nächster Lauf korrigiert es |
| Workflow rot bei „Tests“ | Code auf `main` reparieren; bis dahin keine Datenänderung |
| Seite zeigt Hinweis „seit mehr als drei Stunden“ | Actions prüfen; ggf. Workflow reaktivieren |
| Geplanter Workflow deaktiviert (60 Tage) | Actions → Pipeline → Enable workflow, dann Run workflow |
| Fehlerhafter Bestand | Auf `data-state` den letzten guten Commit wiederherstellen (`git revert`), dann Run workflow |
| `data-state` über 100 MB | Branch manuell auf einen Commit zusammenfassen |

Bei `recovered_fetch_gaps` die protokollierten `seconds` mit `limit_seconds` vergleichen, den vorherigen erfolgreichen Abruf in `data-state/state/runlog.jsonl` und die tatsächlichen `schedule`-Runs unter Actions prüfen. Die Lücke ist ein **historischer Aktualitätsausfall**, kein Beleg für einen aktuell fehlerhaften Quelladapter. Keine zusätzlichen USGS-Abrufe zur Diagnose starten, solange vorhandene Runs/Runlog den Zustand belegen. GitHub-Cron-Lücken separat beheben (unabhängiger Trigger); ein grüner Folge-Lauf löscht den Runlog-Nachweis nicht. Die veröffentlichten Quellen und `public:true` bleiben unverändert.

## 5. Lokale Vorschau mit echten Daten

```
python -m cw run --state /tmp/st
python -m cw snapshot --state /tmp/st --revision 0000000 --out site/data/snapshot.json --include-unreleased
python -m http.server -d site 8000
```
`site/data/` steht in `.gitignore` und wird nie committet.

## Legacy-Testvorschau für künftige private Quellen

- Die reguläre Adresse `/` erhält `_site/data/snapshot.json` und veröffentlicht nur Quellen mit `public:true`. Aktuell sind USGS, NOAA SWPC und die verifizierte GDACS-Abdeckung freigegeben.
- Die frühere separate Seite `/test/` wird **nicht mehr gebaut oder deployt**. `site/test.html` und `cw/test_preview.py` bleiben nur als bewusst streng begrenzte Vorlage erhalten, falls später wieder eine private Quelle getestet werden muss.
- `cw.test_preview` ist absichtlich auf USGS und NOAA beschränkt und verweigert bereits regulär freigegebene Testquellen. Vor einer erneuten Nutzung muss die Allowlist deshalb ausdrücklich an den dann privaten Testfall angepasst und erneut geprüft werden.
- Das interne Artefakt `preview/snapshot.json` darf nie als öffentliche Seite veröffentlicht werden: Es kann nicht freigegebene Quellen enthalten. Interne `ingest`-Daten, Rohantworten und Zugangsdaten bleiben ebenfalls unveröffentlicht.
- Release-Abnahme: vollständige Testsuite grün, regulärer Snapshot enthält nur freigegebene Quellen, Quellenhinweise stimmen mit der tatsächlichen Registry überein, und die mobile Darstellung wird separat visuell geprüft.
