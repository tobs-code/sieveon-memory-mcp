"""Validator audit-trail instrumentation (Phase A).

Passive observability around the FROZEN validate() in trackb_two_stage.py.
This module NEVER modifies requests, prompts, routing, retries or parsing:
it tees transport bytes in the calling process only. The frozen file is
imported, never edited. See docs/batch7_observability_design_v1.json.

P1: per-attempt tee (request bytes, response bytes, _router metadata,
    including transport-failed attempts).
P2: per-request router provenance persisted inside each trail entry, plus
    optional before/after counter snapshots (no router code touched).
P3 (run-record schema extension): explicitly NOT implemented here.

Behavior-invariance argument (see audit): every exception validate() could
raise without the tee is re-raised unchanged; the only new code in the
transport path is byte-copying plus a rebuild validate() cannot
distinguish from the original response (it only calls .read()).
"""

import io
import json
import os
import time
import urllib.request as _U

PROMPT_VERSION = "trackb_two_stage.VALIDATOR_PROMPT@HEAD-d533989-plus-local-provider-override"
PROMPT_LOCATION = "scripts/trackb_two_stage.py:VALIDATOR_PROMPT"


def _decode(data):
    if data is None:
        return None
    try:
        return data.decode("utf-8", "replace")
    except Exception:
        return None


def _safe_router_meta(body_bytes):
    try:
        meta = (json.loads(body_bytes).get("_router", {}) or {})
        return {"provider": meta.get("provider"),
                "provider_model": meta.get("model"),
                "router_request_id": meta.get("request_id")}
    except Exception:
        return {"provider": None, "provider_model": None,
                "router_request_id": None}


def _wrap_transport(real_urlopen, attempts):
    """Return a urlopen replacement that records every attempt.

    Transport exceptions are recorded AND re-raised unchanged, so
    validate()'s retry logic observes exactly the failures it would
    observe without instrumentation.
    """
    def one_call(req, *args, **kwargs):
        started = time.time()
        try:
            req_body = req.data
        except Exception:
            req_body = None
        entry = {"request": {"url": req.full_url,
                             "request_body": _decode(req_body)},
                 "response": {"raw_response": None, "router": None},
                 "latency_ms": None,
                 "transport_error": None}
        try:
            resp = real_urlopen(req, *args, **kwargs)
        except Exception as exc:
            entry["transport_error"] = str(exc)[:200]
            entry["latency_ms"] = round((time.time() - started) * 1000, 1)
            attempts.append(entry)
            raise
        try:
            body = resp.read()
        except Exception as exc:
            entry["transport_error"] = "read-failed: %s" % str(exc)[:150]
            entry["latency_ms"] = round((time.time() - started) * 1000, 1)
            attempts.append(entry)
            raise
        entry["response"]["raw_response"] = _decode(body)
        entry["response"]["router"] = _safe_router_meta(body)
        entry["latency_ms"] = round((time.time() - started) * 1000, 1)
        attempts.append(entry)
        try:
            return _U.addinfourl(io.BytesIO(body), resp.headers,
                                  resp.url, resp.status)
        except Exception:
            # Practically unreachable (BytesIO rebuild); fallback preserves
            # exactly what validate() observes (a single .read() of body).
            return _U.addinfourl(io.BytesIO(body), {}, req.full_url, 200)
    return one_call


def run_trailed(items, validate_fn, urlopen_module=_U,
                  prompt_version=None, prompt_location=None):
    """Run frozen validate() per item, return (results, trail).

    items: list of {probe_item_id, sentence_id, text, subject, object,
                    sentence_gold, pair_gold}.
    validate_fn: the FROZEN validate function (called unmodified).
    """
    real_urlopen = urlopen_module.urlopen
    results = []
    trail = []
    for it in items:
        attempts = []
        urlopen_module.urlopen = _wrap_transport(real_urlopen, attempts)
        outcome = {"supported": None, "technical_failure": None}
        try:
            try:
                supported, _raw_prefix = validate_fn(
                    it["text"], it["subject"], it["object"])
                outcome["supported"] = bool(supported)
            except Exception as exc:
                outcome["technical_failure"] = str(exc)[:200]
        finally:
            urlopen_module.urlopen = real_urlopen
        results.append({"probe_item_id": it["probe_item_id"],
                        "supported": outcome["supported"],
                        "technical_failure": outcome["technical_failure"]})
        trail.append({
            "probe_item_id": it["probe_item_id"],
            "sentence_id": it.get("sentence_id"),
            "subject": it["subject"],
            "object": it["object"],
            "sentence_gold": it.get("sentence_gold"),
            "pair_gold": it.get("pair_gold"),
            "prompt_version": prompt_version or PROMPT_VERSION,
            "prompt_location": prompt_location or PROMPT_LOCATION,
            "router_mode": os.getenv("TRACKB_VALIDATOR_MODEL",
                                     "auto-private"),
            "attempts": attempts,
            "parser_result": {
                "note": "parsing lives inside frozen validate(); "
                        "supported mirrors its return; full raw replies "
                        "are preserved per attempt above",
            },
            "final_validator_decision": outcome["supported"],
            "technical_failure": outcome["technical_failure"],
        })
    return results, trail
