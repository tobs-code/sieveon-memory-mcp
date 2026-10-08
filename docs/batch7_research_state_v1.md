# Batch-6 / Batch-7 Forschungsstand (Statusdokument, unveränderlich)

Version: `batch7_research_state_v1` — Abschluss- und Übergabepunkt, kein Versuchsartefakt.
Es werden keine Hypothesen aufgestellt und keine Folgeversuche angeordnet.

## 1. Gesicherte Beobachtungen

- Batch 6: 9 von 17 Gold-YES-Sätzen ohne Kandidatenpaar (Fälle prodc6-012/027/030/032/055/112/120/130/132).
- Batch 7: 0 von 4 Gold-YES-Fällen ohne Kandidatenpaar (alle 4 hatten Paare: 1× ACCEPT, 1× ABSTAIN, 1× REJECT bei richtigem Paar, 1× REJECT bei verdrehtem Paar).
- Grobquoten: 9/150 Sätze (B6) vs. 0/73 Sätze (B7).
- Over-generation beidseitig beobachtet: je 13 Sätze mit Kandidat auf Gold-NO (B6 satzweise; B7 17 Records auf 13 Sätzen).
- Candidate Recall: B6 8/17, B7 4/4 (deskriptiv, kein Mechanismusbefund).
- Status: **`not_replicated`, keine Widerlegung.**

## 2. Grenzen der Aussagekraft (methodisch eingeschränkt)

- Unterschiedliche Korpora per Design: B6 Wikipedia (150 Sätze), B7 heterogenes Sachtextkorpus (200 Sätze).
- Vollzensur (B6, alle 150 Sätze, human annotiert) vs. seeded Record-Sample (B7, 80 Records / 73 Sätze, Seed 7, Agent annotiert, blind-to-verdict).
- Asymmetrische Gold-YES-Basis: 17 vs. 4 — die Null in B7 hat begrenzte Präzision.
- Accept-Metriken (ACCEPT/REJECT/ABSTAIN, Recall, Präzision) sind validator-konfundiert (B6 kilo/stepfun vs. B7 lokaler Router groq/zai) und werden nicht batchübergreifend verglichen.
- Silence entsteht vor Validation und ist vom Validatorwechsel unberührt.
- 4 B7-UNCLEAR sind aus der binären Interpretation ausgeschlossen; Record-Level und Sentence-Level werden nicht vermischt (kein pauschaler 80er-Nenner).

## 3. Offene Forschungsfrage (ungeklärt)

Unter welchen Bedingungen tritt der beobachtete Silence-Befund auf, und hängt er systematisch vom Material ab?

Ausdrücklich noch nicht festgelegt: keine neue Hypothese, keine Versuchsanordnung, keine Mechanismusbehauptung. Materialabhängigkeit ist eine offene Erklärungsklasse, keine Erklärung.

## Artefaktkette (alle frozen, unverändert)

Corpus `c820ada6…` → Run `bcfd8280…` (221 Records) → Sample Seed 7 (80 Records) → Gold `0e9a3150…` (72/4/4) → Evaluation (`not_replicated`) → Vergleich `batch6_batch7_comparison_v1` → dieses Dokument.
Provenienzbeilagen: `_unused/log1.txt` (Validator groq/qwen3.8-27b, Router-Modes dokumentiert).
