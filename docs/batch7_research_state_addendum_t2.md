# Addendum T2: rights/duties false-candidate probe (Status, unveränderlich)

Ergänzt `batch7_research_state_v1.md`, ändert es nicht.

## Design

Kontrollierte Minimalpaare (preregistered, `batch7_t2_rights_duties_design_v1`):
8 Paare (16 Sätze), positiv (provides/gives/transfers → YES) vs. negativ
(responsibility/duty/right/authority → NO), gleiche Entitäten, maximal
identischer Rahmen. Direction-Correctness explizit nicht Teil der Probe.

## Befund (`batch7_t2_run_v1.jsonl`, nur `nu_candidates`)

- Positive Kontrolle: 8/8 mit Kandidaten (Probe valide, Gate ≥7/8 erfüllt).
- Negative: 7/8 mit Kandidaten (nur A1 ohne).
- Frames: responsibility 2/2, duty 2/2, right 2/2, authority 1/2 (n=2 pro Zelle, rein deskriptiv).
- Verdict per Kriterium: **`effect`**.

## Abgrenzung (was NICHT gezeigt wurde)

- Gezeigt: Diese Konstruktionen werden als Kandidaten vorgeschlagen.
- Nicht gezeigt: dass der Candidate Generator semantische Provision
  grundsätzlich nicht von Duties unterscheiden kann.
- Keine mechanistische Erklärung (kein „weil …").
- Keine Rückinterpretation von B6/B7 über das Ergebnis hinaus.
- Keine Pipeline-Änderung (diagnostisch, wie vorregistriert).

## Status

T2 geschlossen / effect. T1 (no_effect) und T2 (effect) stehen nebeneinander:
B6-Silence nicht durch Passiv/Oblique erklärt; reproduzierbares
Precision-Problem bei transferähnlichen Nicht-Transfer-Konstruktionen.
Offen und ungeplant: Frame-Abhängigkeit (T2b-Idee), T3, Gate-Mechanismus.
