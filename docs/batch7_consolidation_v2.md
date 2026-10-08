# Konsolidierung v2: Gesamtstand bis V-Probe (Audit, unveränderlich)

Folgt auf `batch7_consolidation_v1.md` (unverändert). Keine neue Messung,
keine Interpretation über die Artefakte hinaus, kein Pipeline-Code, kein Commit.

## Re-Verifikation (dieses Audit, read-only nachgerechnet)

- T1-Run: 24 Records (12 Test + 12 Kontrolle mit Paar) ↔ Addendum T1 korrekt.
- T2-Run: 16 Records (8/8 positiv, 7/8 negativ) ↔ Addendum T2 korrekt.
- T2b-Run: 18 Records (P 6/6, N1 4/6, N2 5/6) ↔ Addendum T2b korrekt.
- V-Probe: 24 Items (A 8/8, B 8/8 rejected, C 4/4 rejected, D separat),
  0 technische Fehler ↔ Eval-Verdict `selective` korrekt.
- Overreach-Check: Volltextsuche nach Generalisierungs-Formulierungen
  („beweist/bewisen/garantiert/immer/generell/löst allgemein") in den
  Research-Docs findet nur Corpus-Snapshot-Texte und explizite
  Nicht-Behauptungen („nicht bewiesen", „gestützt, nicht bewiesen").
  **Kein Fall von `selective` → „Validator löst das Problem allgemein".**

## Hypothesenstand (aktualisiert)

```text
H1  passive/oblique → candidate miss
    T1 no_effect: geschwächt / unter Setup verworfen   [durch Probe gestützt]

H2  Rights/Duties → spezifische semantische Verwechslung
    T2b general_form_effect: geschwächt                 [durch Probe gestützt]

H3  breiter syntaktisch/formaler Trigger
    T2b: gestützt (N2 5/6)                             [durch Probe gestützt]

H4  semantische Präzision wird downstream hergestellt
    V-Probe selective: gestützt, NICHT bewiesen         [durch Probe gestützt]
    (n klein, stark kontrolliert, nur Assertions-Validator, nur groq)
```

## Vier-Kategorien-Markierung

- **Beobachtet:** alle Zählungen oben; B6 9/17 vs. B7 0/4 Silence; Over-generation beidseitig.
- **Durch Probe gestützt:** H1-Verwerfung (T1), H2-Schwächung + H3-Stützung (T2b), H4-Stützung (V-Probe).
- **Nicht getestet:** Validator auf natürlichem (nicht-kontrolliertem) Material;
  Worthiness/Link-Selektivität; T3; End-to-End-Reliabilität („goldenes Triple").
- **Nicht ableitbar:** Mechanismus-Behauptungen; allgemeine Validator-Reliabilität
  aus 24 kontrollierten Items; Satz-Populationsraten aus Probe-Samples;
  „Batch 6 war falsch"; „Hypothese widerlegt".

## Offene Leitfrage (unverändert, nur Frage)

Ist hoher Candidate-Recall + selektiver Validator zusammen ausreichend für
verlässliche End-to-End-Triples inklusive Silence-Verhalten? Erst aus einer
freigegebenen Probe beantwortbar, nicht aus dieser Konsolidierung.
