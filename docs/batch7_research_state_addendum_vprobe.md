# Addendum V-Probe: assertion-validator selectivity (Status, unveränderlich)

Ergänzt `batch7_research_state_v1.md`, ändert es nicht.

## Design

Separates Validator-Probe-Design (`batch7_v1_validator_probe_design_v1`):
24 fixe Paare (A8/B8/C4/D4), ausschließlich `validate()` (frozen),
kein Candidate-Generator-Lauf, Provider-Provenienz pro Request
(durchgehend groq), 0 technische Fehler.

## Beobachtung (`batch7_v1_probe_eval_v1`)

- A true pairs: 8/8 supported (Validity-Gate erfüllt).
- B spurious pairs: 8/8 rejected.
- C reversed pairs: 4/4 rejected (inkl. beobachtetem B7-pos65-Fall).
- D upstream-abstention-eligible: nur Reporting (ABSTAIN-Records 2/2
  supported, bare-plural 0/2) — kein Validator-Abstention-Test.
- Verdict per Kriterium: **`selective`**.

## H4-Bezug (gestützt, nicht bewiesen)

Gestützt: Semantische Selektivität entsteht zumindest teilweise
downstream im Validator (8/8 behalten, 8/8 verworfen, 4/4 Richtung
verworfen — unter diesem Probe-Design, n klein, stark kontrolliert).
Offen: ob bewusstes Architekturdesign oder empirisches Verhalten;
Übertragbarkeit über die Probe hinaus; T2/T2b bleiben unberührt
komplementär (Generator-Breite) statt entkräftet.

## Getrennte Ebenen (nicht vermischen)

- Candidate breadth (T1/T2/T2b: permissiv, recall-orientiert).
- Validator selectivity (V-Probe: 8/8 vs. 8/8).
- Upstream worthiness/abstention (eigene Stufe; D zeigt nur, dass
  `validate()` allein solche Paare teils trotzdem stützt).

Keine Pipelineänderung, kein Gate-Bau, kein neuer Versuch.
