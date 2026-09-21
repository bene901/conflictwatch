# ConflictWatch V6

Amtliche Gefahrenmeldungen als kompakte, mobile Liste. Spezifikation: Rev. 2 (eingefroren).

**Stand:** öffentliche automatische Datenquellen für USGS-Erdbeben, NOAA-Weltraumwetter und GDACS-Zyklone, Fluten, Waldbrände, Vulkane und Dürren.

```
registry.json            Quellen, Skalen, Regeln (USGS, NOAA SWPC, GDACS inkl. VO/DR - public: true)
schema/                  JSON-Schema Rev. 2 (unverändert)
cw/                      Pipeline: Adapter, Zusammenführung, Validierung, Snapshot, CLI
site/                    Website (eine HTML-, eine CSS-, eine JS-Datei; lädt nur data/snapshot.json)
scripts/                 Git-Logik für den Branch data-state
tests/                   Regressionstests mit archivierten echten Quellantworten
.github/workflows/       pipeline.yml (stündlich), ci.yml (Pull Requests)
docs/RUNBOOK.md          Einrichtung, Funktionstest, Betrieb
docs/USGS.md             Belegte Fakten zur USGS-Schnittstelle
```

Lokal: `pip install -r requirements.txt && python -m unittest discover -s tests -t .`
