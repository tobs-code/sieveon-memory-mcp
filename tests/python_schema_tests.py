"""Schema write-path audit against a live SurrealDB.

Runs against a throwaway namespace so the working database is never
touched, and skips cleanly when no server is reachable.

Why this exists: `entity` is declared SCHEMAFULL, and on a SCHEMAFULL
table SurrealDB 3 treats `TYPE object` as schemafull too. A field the
schema does not declare therefore rejects the write outright, which is
how `entity.metadata` broke merge_entities and consolidate on a clean
install while the development database (where entity is SCHEMALESS) looked
perfectly healthy. The failure was invisible in normal testing, so every
real write path is asserted here explicitly.

The namespace is passed per call rather than via the environment:
SURREAL_NS is bound when src.mcp.core is imported, so setting the
environment after import has no effect.
"""

import asyncio
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NS = "sieveon_schema_audit"
ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each case mirrors a statement the application actually issues. Keep these
# in sync with the code that builds them; a new write path belongs here.
WRITE_PATHS = [
    ("entity: minimal (entropy_gate fallback)", """
        CREATE entity:a1 SET name = 'a1', type = 'person',
            created_at = time::now(), updated_at = time::now();"""),
    ("entity: entropy_gate with embedding", """
        CREATE entity:a2 SET name = 'a2', type = 'org',
            created_at = time::now(), updated_at = time::now(),
            embedding = %s;""" % str([0.1] * 1024)),
    ("entity: tools.py merge_entities metadata (flat)", """
        CREATE entity:a4 SET name = 'a4', type = 'person',
            metadata = { action: 'merge_entities', source: 'x',
                         target: 'y', merged: 3, errors: 0 };"""),
    ("entity: tools.py consolidate metadata", """
        CREATE entity:a5 SET name = 'a5', type = 'person',
            metadata = { action: 'consolidate', scope: 'global',
                         stale_facts: 2, deleted: 1,
                         duplicates_merged: 0 };"""),
    ("entity: nested metadata", """
        CREATE entity:a6 SET name = 'a6', type = 'person',
            metadata = { extractor: 'relex', nested: { conf: 0.9 } };"""),
    ("entity: forget path (all declared fields)", """
        CREATE entity:a7 SET name = 'a7', type = 'person',
            forgotten = false, forget_reason = 'test',
            created_at = time::now(), updated_at = time::now();"""),
    ("event: memory_store with metadata", """
        CREATE event:a8 SET content = 'hello', source = 'user_input',
            content_hash = 'abc', embedding = %s,
            metadata = { tool: 'memory_store' };""" % str([0.1] * 1024)),
    ("fact: RELATE with the full entropy_gate field set", """
        RELATE entity:a1->fact->entity:a2 SET
            predicate = 'founded', confidence = 0.9, salience = 0.8,
            extractor = 'relex', source_event = event:a8;"""),
    ("gate_log: decision without salience (pre-v6 shape)", """
        CREATE gate_log SET content_hash = 'h', text_score = 0.5,
            novelty = 0.1, compression_ratio = 0.2, gate_score = 0.6,
            decision = 'extract', reason = 'r', threshold = 0.5;"""),
    ("gate_log: decision with salience (v6 shape)", """
        CREATE gate_log SET content_hash = 'h2', text_score = 0.5,
            novelty = 0.1, compression_ratio = 0.2, gate_score = 0.6,
            decision = 'skip', reason = 'r', threshold = 0.5,
            salience = 0.7, salience_version = 'v1';"""),
    ("router_costs: UPSERT nested state", """
        UPSERT router_costs:state CONTENT { state: { version: 1,
            metrics: { factual: { semantic_hybrid: { total_count: 2 } } } },
            updated_at: time::now() } RETURN NONE;"""),
    ("entity: forgotten backfill", """
        UPDATE entity SET forgotten = false WHERE forgotten IS NONE;"""),
    ("entity: timestamp backfill", """
        UPDATE entity SET created_at = time::now() WHERE created_at IS NONE;"""),
]


async def _q(sql, params=None):
    """Query the throwaway namespace, bypassing the configured database."""
    from src.mcp.core import _query_surreal
    return await _query_surreal(sql, params, ns=NS, db=NS)


def _schema_statements():
    """docs/schema.surql split into statements, comments stripped."""
    statements, current = [], ""
    for raw in (ROOT / "docs" / "schema.surql").read_text(
            encoding="utf-8").splitlines():
        line = raw.split("--")[0] if raw.strip().startswith("--") else raw
        current += line + "\n"
        if line.strip().endswith(";"):
            if current.strip():
                statements.append(current.strip())
            current = ""
    if current.strip():
        statements.append(current.strip())
    return statements


def _server_available():
    try:
        import httpx
        url = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
        auth = (os.getenv("SURREALDB_USER", "root"),
                os.getenv("SURREALDB_PASS", "root"))
        return httpx.get(url.replace("/sql", "/health"), auth=auth,
                         timeout=3.0).status_code == 200
    except Exception:
        return False


@unittest.skipUnless(_server_available(), "no SurrealDB server reachable")
class TestSchemaWritePaths(unittest.TestCase):
    """Every real write path must succeed against a freshly loaded schema."""

    @classmethod
    def setUpClass(cls):
        async def _setup():
            import src.mcp.core as core
            from src.mcp.migrations import MigrationEngine, _register_builtin

            # Other suites in the same process deliberately fail queries,
            # which can leave the (module-global) breaker open and make every
            # later DB test fail for _CIRCUIT_RESET_AFTER seconds even though
            # the database is healthy. SURREALDB_DISABLE_CIRCUIT_BREAKER=1
            # short-circuits it; the explicit reset covers the default path.
            core._CIRCUIT_BREAKER_DISABLED = True
            core.reset_surreal_circuit()

            for stmt in _schema_statements():
                try:
                    await _q(stmt)
                except Exception:
                    pass  # IF NOT EXISTS against an already-defined object

            engine = MigrationEngine(_q)
            _register_builtin(engine)
            await engine.apply_all()

        asyncio.run(_setup())

    @classmethod
    def tearDownClass(cls):
        async def _teardown():
            import src.mcp.core as core
            core._CIRCUIT_BREAKER_DISABLED = False
            core.reset_surreal_circuit()
            await _q(f"REMOVE DATABASE IF EXISTS {NS};")

        try:
            asyncio.run(_teardown())
        except Exception:
            pass

    def test_all_write_paths_accepted(self):
        async def _run():
            failures = []
            for label, sql in WRITE_PATHS:
                try:
                    await _q(sql)
                except Exception as exc:
                    failures.append(f"{label}: {str(exc)[:160]}")
            return failures

        failures = asyncio.run(_run())
        self.assertEqual(
            failures, [],
            "schema rejects declared write paths (a SCHEMAFULL table rejects "
            "any field it does not declare):\n  " + "\n  ".join(failures))

    def test_nested_metadata_round_trips(self):
        """A write succeeding is not enough -- the data must survive."""
        async def _run():
            await _q("CREATE entity:rt SET name = 'rt', type = 'person', "
                     "metadata = { action: 'merge_entities', nested: { k: 1 } };")
            for item in await _q("SELECT metadata FROM entity:rt;"):
                result = item.get("result") if isinstance(item, dict) else None
                if isinstance(result, list) and result:
                    return result[0].get("metadata")
            return None

        meta = asyncio.run(_run())
        self.assertIsNotNone(meta, "metadata did not read back")
        self.assertEqual(meta.get("action"), "merge_entities")
        self.assertEqual(meta.get("nested"), {"k": 1})

    def test_declarations_need_no_repair_path(self):
        """The declared schema must stand on its own.

        ensure_schema_loaded() re-applies entity fields with OVERWRITE, which
        would repair a schema.surql that forgot FLEXIBLE and mask the defect.
        So assert the declarations themselves, without the repair.
        """
        import re
        sources = {
            "schema.surql": ROOT / "docs" / "schema.surql",
            "baseline migration": ROOT / "src" / "mcp" / "migrations.py",
        }
        for label, path in sources.items():
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if re.search(r"metadata ON entity TYPE", line):
                    self.assertIn(
                        "FLEXIBLE", line,
                        f"{label}: entity.metadata is schemafull without "
                        f"FLEXIBLE and rejects every write that carries "
                        f"metadata: {line.strip()}")
                    break
            else:
                self.fail(f"{label}: entity.metadata not found")

    def test_object_fields_on_schemafull_tables_are_flexible(self):
        """General rule, so the next field added here cannot repeat the bug.

        On a SCHEMAFULL table an object field accepts only keys the schema
        declares unless it is marked FLEXIBLE.
        """
        import re
        text = (ROOT / "docs" / "schema.surql").read_text(encoding="utf-8")
        current = None
        for raw in text.splitlines():
            line = raw.split("--")[0].strip()
            m = re.match(
                r"DEFINE TABLE IF NOT EXISTS (\w+) (SCHEMAFULL|SCHEMALESS)", line)
            if m:
                current = (m.group(1), m.group(2) == "SCHEMAFULL")
                continue
            m = re.match(r"DEFINE FIELD (?:IF NOT EXISTS )?(\w+) ON (\w+) "
                         r"TYPE (?:none \| |option<)?object>?", line)
            if m and current and current[1]:
                self.assertIn(
                    "FLEXIBLE", line,
                    f"{current[0]}.{m.group(1)} is SCHEMAFULL and must be "
                    f"FLEXIBLE to accept arbitrary keys: {line}")


class TestCircuitBreakerEscapeHatch(unittest.TestCase):
    """The breaker is module-global, so it needs a way to be switched off.

    Without it, a suite that deliberately triggers failures makes every
    later DB test fail for _CIRCUIT_RESET_AFTER seconds even though the
    database is fine -- the symptom looks like a schema problem, which is
    exactly what wasted time here.
    """

    def test_disabled_flag_skips_the_open_check(self):
        """With the breaker disabled, an open circuit must not raise."""
        import src.mcp.core as core

        saved = core._CIRCUIT_BREAKER_DISABLED
        try:
            core._surreal_circuit_open = True
            core._surreal_failure_count = core._CIRCUIT_OPEN_THRESHOLD + 1
            core._surreal_last_failure = 1e12  # far in the future

            core._CIRCUIT_BREAKER_DISABLED = True
            # Must not raise the "circuit open" error; the HTTP call is
            # replaced so this stays a pure unit test.
            async def _run():
                class _Resp:
                    status_code = 200

                    def json(self):
                        return [{"status": "OK", "result": None}]

                class _Client:
                    async def post(self, *a, **kw):
                        return _Resp()

                async def _client():
                    return _Client()

                saved_client = core._get_client
                saved_retry = core._budget_aware_should_retry
                core._get_client = _client
                core._budget_aware_should_retry = lambda s: 1
                try:
                    await core._query_surreal("SELECT 1;")
                finally:
                    core._get_client = saved_client
                    core._budget_aware_should_retry = saved_retry

            asyncio.run(_run())
        finally:
            core._CIRCUIT_BREAKER_DISABLED = saved
            core.reset_surreal_circuit()

    def test_enabled_by_default_and_read_from_environment(self):
        import src.mcp.core as core
        # Off unless explicitly requested: production depends on it.
        self.assertFalse(core._CIRCUIT_BREAKER_DISABLED,
                         "circuit breaker must stay on unless opted out")

    def test_reset_clears_all_state(self):
        import src.mcp.core as core
        core._surreal_failure_count = 9
        core._surreal_circuit_open = True
        core._surreal_backoff_level = 7
        core._surreal_last_failure = 123.0
        core.reset_surreal_circuit()
        self.assertEqual(core._surreal_failure_count, 0)
        self.assertFalse(core._surreal_circuit_open)
        self.assertEqual(core._surreal_backoff_level, 0)
        self.assertEqual(core._surreal_last_failure, 0.0)

    def test_env_flag_is_read(self):
        """The flag must be driven by the environment, not hardcoded."""
        import os
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / "src" / "mcp" / "core.py").read_text(encoding="utf-8")
        self.assertIn("SURREALDB_DISABLE_CIRCUIT_BREAKER", text)


if __name__ == "__main__":
    unittest.main()