-- ========================================
-- Testdaten für das Agent-Native Memory System
-- ========================================

USE NS agent_memory DB agent_memory;

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
RELATE entity:alice->fact:works_at->entity:acme_corp SET
    valid_from = time::now() - 5d,
    confidence = 1.0,
    source_event = (SELECT id FROM event WHERE content CONTAINS "arbeite bei Acme Corp").id;

RELATE entity:alice->fact:knows->entity:bob SET
    valid_from = time::now() - 3d,
    confidence = 0.9;

RELATE entity:alice->fact:working_on->entity:projekt_x SET
    valid_from = time::now() - 2d,
    confidence = 0.95;

-- 4. Test der Helper-Functions
-- fn::active_fact
SELECT * FROM fn::active_fact(entity:alice, "works_at");

-- fn::temporal_context
SELECT * FROM fn::temporal_context(entity:alice, 3h);
