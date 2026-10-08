# Konsolidierung: Candidate-Generation-Probes T1 / T2 / T2b (Status, unveränderlich)

Stand nach T2b. Keine neuen Messungen, keine Pipelineänderung, kein Gate-Bau.

## A — Eingefrorene Befunde

- **B6/B7 Ausgang:** B6 9/17 Gold-YES ohne Paar; B7 0/4. `not_replicated`, keine Widerlegung.
- **T1** (Passiv + Oblique, 12 Paare): Kontrolle 12/12, Test 12/12 → **`no_effect`**.
- **T2** (Rights/Duties, 8 Paare): Positive 8/8, Negative 7/8 → **`effect`**.
- **T2b** (Frame-Kontrolle, 6 Triples): P 6/6, N1 4/6, N2 5/6 → **`general_form_effect`** (nicht frame-spezifisch).
- Alle Proben liefen ausschließlich über `nu_candidates`. Keine Probe hat den Validator getestet.

## B — Hypothesenstand

```text
H1  passive/oblique → candidate miss
    T1: geschwächt / unter diesem Setup verworfen

H2  Rights/Duties → spezifische semantische Verwechslung
    T2b: geschwächt (Effekt nicht frame-spezifisch)

H3  breiter syntaktisch/formaler Trigger
    T2b: gestützt (N2 5/6 liegt über der Frame-spezifischen Erwartung)

H4  semantische Präzision wird downstream hergestellt
    OFFEN (bisher kein Validator-Experiment)
```

Explizit **nicht** bewiesen: irgendein Mechanismus. Explizit **nicht** geändert: irgendeine Pipeline.

## C — Nächste Messfrage (nur Frage, kein Versuchsaufbau)

Wo entsteht die eigentliche Selektivität: bereits bei der Candidate
Generation oder erst beim Validator?

Hintergrund: Der gesamte bisherige Testpfad (`sentence → nu_candidates`)
vermisst nur die Generierung. Ob der nachgelagerte Validator kontrolliert
erzeugte False Candidates (T2/T2b-Material) zuverlässig aussortiert, ist
unbekannt. Ein Validator-Probe-Design darf erst aus diesem Dokument
abgeleitet werden, nicht aus den Rohbefunden allein.

Beweismittel: `batch7_t1_run_v1.jsonl`, `batch7_t2_run_v1.jsonl`,
`batch7_t2b_run_v1.jsonl`, Designs und Addenda im selben Verzeichnis.
