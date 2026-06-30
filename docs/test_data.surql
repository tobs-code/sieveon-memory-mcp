-- ========================================
-- Testdaten für das Agent-Native Memory System
-- ========================================

USE NS strata DB strata;

-- 1. Events hinzufügen (Append-Only)
CREATE event SET
    source = "user_input",
    content = "Ich heiße Alice und arbeite bei Acme Corp.",
    timestamp = time::now() - 2h;

CREATE event SET
    source = "user_input",
    content = "Heute habe ich einen Vertrag unterschrieben.",
    timestamp = time::now() - 1h;

CREATE event SET
    source = "user_input",
    content = "Morgen werde ich mit Bob über das Projekt sprechen.",
    timestamp = time::now() - 30m;

-- 2. Entitäten erstellen
CREATE entity:alice SET
    name = "Alice",
    type = "person";

CREATE entity:bob SET
    name = "Bob",
    type = "person";

CREATE entity:acme_corp SET
    name = "Acme Corp",
    type = "organization";

CREATE entity:projekt_x SET
    name = "Projekt X",
    type = "concept";

-- 3. Facts (Kanten) mit Temporal Validity hinzufügen
CREATE fact SET
    in = entity:alice,
    out = entity:acme_corp,
    predicate = "works_at",
    valid_from = time::now() - 5d,
    confidence = 1.0;

CREATE fact SET
    in = entity:alice,
    out = entity:bob,
    predicate = "knows",
    valid_from = time::now() - 3d,
    confidence = 0.9;

CREATE fact SET
    in = entity:alice,
    out = entity:projekt_x,
    predicate = "working_on",
    valid_from = time::now() - 2d,
    confidence = 0.95;
