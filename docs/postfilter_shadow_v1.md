# PostFilter Shadow v1/v2 — Spezifikation (keine Verhaltensänderung)

## v2-Änderungen (Shadow v2)

1. `ARGUMENT_GROUNDING` (Subjekt-/Objekt-Spans) getrennt von
   `TRIGGER_LICENSING` (Relationstrigger mit Konstruktion).
2. Trigger-Licensing als (Lemma, Konstruktion)-Tabelle statt Wortliste;
   `carry/move/paint/repair` nur in `benefactive-for`-Konstruktion
   (X Ved NP for Y, performed action), sonst lizenzieren sie nichts.
3. Neue Scope-Klassen: `CONTRASTIVE_TARGET` (instead of/rather than),
   `DESIDERATIVE` (hoped/wished/desired/wanted). `instead of` nicht mehr
   unter HYPOTHETICAL versteckt.

## Gate-Reihenfolge (alle Stufen nur protokolliert, nichts verworfen)

```text
CANDIDATE → ANCHOR → ROLE → SCOPE → ENTITY → NLI (shadow) → GRAPH (unverändert)
```

## Stufen

### 1. ANCHOR — Mentions, nicht kanonische Namen
`subject_mention`/`object_mention` als Char-Spans im Satz; zusätzlich
`trigger_span` (provides-Lexem: help/support/encourage/guide/mentor/advocate/
give/fund/...). Kein Literalcheck auf „provides".

### 2. ROLE — semantische Rollenbindung
Positions-/Rollenprüfung Subjekt < Trigger < Objekt (mit dokumentierten
Varianten wie Passiv). Fängt wrong-subject/wrong-direction.

### 3. SCOPE — ASSERTION_SCOPE mit Untergründen
NEGATED / SPECULATIVE / REPORTED / ATTRIBUTED / HYPOTHETICAL /
CONDITIONAL / INTENTIONAL / QUESTIONED. Negation und Attribution strikt
getrennt (Cue ≠ Scope; `denied helping` ≠ `did not help`).

### 4. ENTITY — Resolution statt Blacklist
Keine generische String-Blacklist. `0 Kandidaten = NO_ENTITY`,
`1 = RESOLVED`, `≥2 = ABSTAIN` (bestehender `Jon → AMBIGUOUS`-Pfad).
Track-B-Triples durchlaufen denselben Gate (mitgebrachte Span-Provenance
wird weitergereicht, nicht neu berechnet).

### 5. NLI — Shadow Mode
`nli-MiniLM2`: Label (entailment/contradiction/neutral) + Margin, **ohne**
Schwellenentscheidung. Hypothese: „X provides support to Y". Dient der
Fehlerklassen-Analyse, nicht dem Filtern. Hypothese enthält bewusst die
Ontologie-Definition (Mentoring = provides?), daher kein Gatekeeper.

### 6. GRAPH — unverändert
Schema/Dedup wie bisher; SHACL-artige Checks gehören hierher, nicht in
den Text-Filter.

## Output pro Kandidat

```json
{"anchor": "pass", "role": "pass", "scope": "pass",
 "entity": "pass", "nli": {"label": "entailment", "margin": 0.91}}
```

bzw. bei Scope-Fail: `{"scope": "fail", "reason": "ATTRIBUTED"}`.

## Danach: Filter-Ablation

| Filter | FP entfernt | TP verloren | neue ABSTAIN | Fehlerklasse |
|--------|----------:|----------:|-----------:|--------------|
| Anchor | ? | ? | ? | grounding |
| Role | ? | ? | ? | wrong subject/object |
| Scope | ? | ? | ? | negation/intent/etc. |
| Entity | ? | ? | ? | resolution |
| NLI | ? | ? | ? | semantic |
