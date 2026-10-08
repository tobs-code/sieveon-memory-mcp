# Addendum E2E: Behauptungsfähigkeit + Validator-Recall-Grenze (Status, unveränderlich)

Ergänzt `batch7_research_state_v1.md`, ändert es nicht.

## E2E-Befund (`batch7_e2e_eval_v1`, 32 Sätze, Probe valide 7/8)

TRUE_ACCEPT 12, FALSE_SILENCE 4, FALSE_ACCEPT 0, TRUE_SILENCE 16.
System auf der „lieber Klappe halten"-Seite: 0 False Accepts bei 25 % False Silence.

## False-Silence-Audit (`batch7_e2e_falsesilence_audit_v1`)

| Fall | Befund |
| ---- | ------ |
| E2   | Validator-FN, promptgedeckt (kanonisches TRUE-easy-Paar, keine Exclusion) |
| H5   | Validator-FN, promptgedeckt (explizites provides-X-with-Y, keine Exclusion) |
| H4   | Gold/Prompt-Divergenz möglich (Emissionssinn vs. Prompt-Kategorien) |
| H6   | Gold/Prompt-Divergenz möglich (Awareness vs. Prompt-Kategorien) |

Upstream (Candidate/Linking/Worthiness/Postfilter) in allen 4 Fällen ausgeschlossen.

## H4-Präzisierung

„Der Validator ist selektiv" bleibt gestützt (V-Probe + E2E 16/16 FALSE-Stille).
„Der Validator ist zuverlässig für alle promptgedeckten TRUE-Relationen" ist
widerlegt — für E2/H5 kontrolliert nachgewiesen. Candidate Recall allein
reicht nicht: Die letzte Gate-Stufe kann echte Relationen verwerfen.

## Offene Grenze (Observability-Limit, kein Versuchsfehler)

Das System persistiert das Validator-Urteil (`assertion_status`), aber nicht
die Raw-Reply. Der interne Entscheidungsgrund der 2 sicheren FNs ist daher
nicht rekonstruierbar. Engineering-Befund: Urteil ohne Begründung speichern
genügt nicht für spätere Ursachenanalyse. Für diesen Frozen-Versuch als offene
Grenze dokumentiert; kein Prompt-Fix, kein Gold-Angleich, kein Re-Run.

## Status

E2E geschlossen. Keine Pipelineänderung, kein Gate-Bau, kein neuer Versuch.
