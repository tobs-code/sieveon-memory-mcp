# Addendum T2b: frame-control probe (Status, unveränderlich)

Ergänzt `batch7_research_state_v1.md`, ändert es nicht.

## Design

Kontroll-Triples (preregistered, `batch7_t2b_frame_control_design_v1`):
6 Triples (18 Sätze), Arm P (echter Transfer → YES) vs. Arm N1
(Rights/Duties → NO) vs. Arm N2 (non-relationale Adjunct-Kontrolle
ohne Rights/Duties-Frame → NO). Frage: trägt der Frame den T2-Effekt
oder die allgemeine syntaktische Form?

## Befund (`batch7_t2b_run_v1.jsonl`, nur `nu_candidates`)

- P: 6/6 mit Kandidaten (Probe valide, Gate ≥5/6 erfüllt).
- N1 Rights/Duties: 4/6 mit Kandidaten.
- N2 Adjunct-Kontrolle: 5/6 mit Kandidaten.
- Verdict per Kriterium: **`general_form_effect`**
  (`frame_specific` erfordert N2 ≤1/6 — nicht erfüllt;
  keine Prioritätswahl nötig, Kriterien schließen sich hier aus).

## Abgrenzung (was NICHT gezeigt wurde)

- Gezeigt: Auch semantisch nicht-relationale NO-Konstruktionen
  ähnlicher Form erzeugen häufig Kandidaten (5/6).
- Nicht gezeigt: irgendeine mechanistische Erklärung („weil …").
- T2 (`effect`) bleibt unverändert frozen; T2b widerlegt T2 nicht,
  sondern zerlegt die Frame-Spezifitätsfrage: Der Effekt ist mit
  diesem Design nicht spezifisch für Rights/Duties.
- Keine Pipeline-Änderung (diagnostisch, wie vorregistriert).

## Status

T2b geschlossen / general_form_effect.
Arbeitshypothese für später (nicht entschieden): Candidate Generation
ist recall-orientiert großzügig; semantische Präzision gehört in
nachgelagerte Gates. Kein Gate-Bau, kein Fix, kein T3.
