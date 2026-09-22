# Konfliktquellen: UCDP Candidate und GDELT 2.0

Stand: 22.09.2026.

UCDP Candidate ist ein vorläufiger, kuratierter Monatsbestand organisierter
tödlicher Gewalt. Quellwerte werden nicht stillschweigend korrigiert. Falls
Todesfall-Schätzungen intern widersprüchlich sind, bleiben die Originalwerte
erhalten und der Widerspruch wird markiert.

GDELT 2.0 Events ist automatische Nachrichten-Ereigniserkennung. Diese Ebene
heißt in der Oberfläche ausdrücklich automatisch/ungeprüft. Ein GDELT-Marker ist
weder eine Bestätigung eines Angriffs noch eine ConflictWatch-Eskalationsbewertung.
Es gibt keinen eigenen Eskalationsscore aus Meldungsmenge, Tonalität oder
Goldstein-Wert.

## UCDP Candidate

Der Adapter beginnt auf der offiziellen Downloadseite und ermittelt dort die
neueste monatliche Candidate-CSV-Version. Übernommen werden stabile ID,
Gewaltart, Parteien, Beginn/Ende, Datums- und Ortsgenauigkeit,
Quellkoordinaten sowie untere/beste/obere Todesfall-Schätzung.

where_prec=1 wird als Punkt behandelt, where_prec=6 als Länderebene. Die
Stufen 2 bis 5 sowie 7 (internationale Gewässer/Luftraum) bleiben als
regionale/ungefähre Lage. ConflictWatch geokodiert nichts hinzu.

Die Kartenansicht bewertet den Monatsbestand relativ zum neuesten Ereignis der
Datei. Sonst würde der Live-Zeitfilter einen korrekt veröffentlichten
Monatsbestand vollständig ausblenden.

Attribution: UCDP Candidate Events Dataset, CC BY 4.0. Zusätzlich wird die
von UCDP für Candidate angegebene Publikation zitiert: Hegre, Håvard; Mihai
Croicu; Kristine Eck; Stina Högbladh (2020), "Introducing the UCDP Candidate
Events Dataset", Research & Politics.
Quelle: https://ucdp.uu.se/downloads/

## GDELT 2.0

Der Adapter liest lastupdate.txt und lädt den neuesten sowie sieben vorherige
15-Minuten-Exports. Die Überlappung verhindert Lücken zwischen den stündlichen
ConflictWatch-Abrufen. GLOBALEVENTID dedupliziert überlappende Fenster.

Der Filter ist strukturell, keine Risikobewertung: IsRootEvent=1 plus die
CAMEO-Gruppen 138, 139, 152, 154 und 190 bis 196. Auch danach bleibt die
automatische Klassifikation ungeprüft.

ActionGeo wird nie als bestätigter Einschlagsort interpretiert. Country-Geocodes
bleiben Länderebene, andere GDELT-Geocodes werden als regionale/ungefähre Lage
dargestellt. Fehlende Koordinaten bleiben unverortet statt durch
Landesmittelpunkte ersetzt zu werden.

Ereignisdatum (SQLDATE) und Erfassungszeit (DATEADDED) bleiben getrennt.
