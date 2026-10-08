# Batch 7 + 8 Synthese: zulässige Aussagen (Status, unveränderlich)

Keine neue Probe, keine Änderung, kein Run, kein Commit.

## Beobachtet (observed)

- B6 9/17 vs. B7 0/4 Gold-YES ohne Paar (`not_replicated`, keine Widerlegung).
- T1 12/12-12/12 (`no_effect`); T2 8/8 + 7/8 (`effect`);
  T2b 6/6-4/6-5/6 (`general_form_effect`).
- V-Probe `selective` (8/8 vs. 8/8, alle groq, 0 Tech-Fehler).
- E2E 12/4/0/16 (Probe valide 7/8); alle 4 False-Silences mit produziertem Paar.
- E2/H5: reproduzierte prompt-gedeckte MODEL_DENIAL (Ast G 3/3, Trails vollständig).
- Ast D `goods`: flipt E2+H5 (zu breit, verworfen).
- Ast I `material supplies`: E2 gefixt, Rest stabil (`SAFE_IMPROVEMENT`, n=6 Items).
- Ast J: `PROBE_INVALID` (A bereits 4/6).
- Batch-8-Codierung: E2 fram-typisch/verb-unikat; H5 fram-unikat/inanimat;
  keine gemeinsame FN-Oberfläche; kein Diskriminator.

## Demonstriert (demonstrated, im jeweiligen Setup)

- Audit-Trail-Instrumentierung unter Live-Traffic (P1/P2, 24/24 + 18/18 + 12/12).
- Validator-Reproduzierbarkeit unter Setup (Ast G).
- Change-Safety-Anwendung (Ast H-Gates griffen: goods als zu breit erkannt).
- Lokaler E2-Fix mit Safety-Zaun (Ast I).

## Nicht demonstriert (not demonstrated)

- H-SUPPLY-Generalisierung (Ast J invalid, nicht negativ bewiesen).
- Gemeinsame Ursache E2/H5 (Heterogenität offengelegt, ungetestet).
- Linguistischer FN-Diskriminator (n=2 lässt keinen zu).
- FA-Sicherheit jenseits getesteter Scopes (keine Populationsaussage).
- Interner Entscheidungsmechanismus (keine Begründung emittiert).

## Nicht inferierbar (unknowable mit aktuellem Instrumentarium)

- Warum das Modell intern E2/H5 ablehnt (keine Reasoning-Outputs).
- Ob E2/H5 dieselbe Ursache teilen.
- Ob `material supplies` über die 6 Items hinaus trägt.

## Ehrliche Endposition

E2/H5 sind zwei reproduzierte Fehlverhalten, deren Ursache sich mit dem
vorhandenen Instrumentarium nicht sauber auseinanderziehen lässt.
Kein weiterer Probe-Ast ohne separat genehmigte, neu begründete Messfrage.
