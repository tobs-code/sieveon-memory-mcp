"""Boundary and failure-injection tests for the triple accept pipeline.

The pipeline decides per extraction confidence, so the boundaries are where
the policy lives or breaks:

    conf <  0.70            drop, model never sees it
    0.70 <= conf <= 0.95    verifier decides (margin >= 6.2617 accepts)
    conf >  0.95            auto-accept

A float that lands exactly on 0.70 or 0.95 must go to the documented side:
0.70 is judged, 0.95 is accepted. "<" versus "<=" at either edge changes
which triples reach the graph, and a refactor that moves one comparison
must fail here loudly rather than drift silently.

Failure injection covers the same question from the other side: when the
verifier is unavailable, no unjudged 0.70-0.95 triple may reach the graph.
Dropping them is the safe direction; letting them through would store facts
nobody checked.

None of these tests loads a model. The verifier is stubbed, because what is
under test is the routing around the model -- which triples reach it, which
bypass it, and what happens when it is gone.
"""

import unittest

from src.extraction.verbalise import BAND_HI, BAND_LO
from src.extraction.verifier import _ACCEPT_MARGIN


def _triple(conf, predicate="uses", subject="A", obj="B"):
    return {"subject": subject, "predicate": predicate, "object": obj,
            "confidence": conf}


def _run_with_stub(triples, margin=None, broken=False):
    """Run verify_triples with a stubbed model.

    margin: the entailment-minus-contradiction margin the stub returns.
    broken: the stub raises instead of answering.
    """
    import numpy as np
    import src.extraction.verifier as vf

    orig = vf._get_verifier

    class _Stub:
        def predict(self, pairs, convert_to_numpy=True):
            if broken:
                raise RuntimeError("verifier unavailable")
            return np.array([[0.0, margin, 0.0] for _ in pairs])

    vf._get_verifier = lambda: (_Stub(), 1, 0)
    try:
        return vf.verify_triples("Some sentence here.", triples)
    finally:
        vf._get_verifier = orig


class TestBandBoundaries(unittest.TestCase):
    """0.70 is judged, 0.95 is judged, above 0.95 accepts.

    The band is closed on both ends, matching the eval that measured it:
    in-band means BAND_LO <= conf <= BAND_HI, and the adoption numbers were
    computed with exactly those bounds. Moving either edge would invalidate
    the measurement, so the edges are pinned here.
    """

    def test_below_floor_drops_without_model_contact(self):
        accepted, dropped = _run_with_stub([_triple(0.6999)], margin=99.0)
        self.assertEqual(accepted, [])
        self.assertEqual(dropped, 1)

    def test_floor_is_judged_not_dropped(self):
        # A margin far above the bar, so acceptance proves the triple
        # reached the verifier rather than bypassing it.
        accepted, dropped = _run_with_stub([_triple(0.70)], margin=99.0)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(dropped, 0)
        self.assertIsNotNone(accepted[0].get("verifier_margin"))

    def test_ceiling_is_judged_not_accepted(self):
        # The band is closed: 0.95 is still judged. A margin far below the
        # bar proves it, because acceptance here would mean a bypass.
        accepted, dropped = _run_with_stub([_triple(0.95)], margin=-99.0)
        self.assertEqual(accepted, [])
        self.assertEqual(dropped, 1)

    def test_above_ceiling_accepts_without_a_margin(self):
        accepted, dropped = _run_with_stub([_triple(0.9501)], margin=-99.0)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(dropped, 0)
        self.assertIsNone(accepted[0].get("verifier_margin"))

    def test_float_just_inside_each_edge(self):
        # 0.7000001 judges, 0.9499999 judges: the edges are inclusive and
        # float noise around them must not flip the branch.
        for conf in (0.7000001, 0.9499999):
            accepted, dropped = _run_with_stub([_triple(conf)], margin=99.0)
            self.assertEqual(len(accepted), 1, f"conf={conf} not judged")
            self.assertIsNotNone(accepted[0].get("verifier_margin"))


class TestAcceptMargin(unittest.TestCase):
    """The margin bar itself, at and around the measured value."""

    def test_at_margin_accepts(self):
        accepted, dropped = _run_with_stub(
            [_triple(0.80)], margin=_ACCEPT_MARGIN)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(dropped, 0)

    def test_just_below_margin_drops(self):
        accepted, dropped = _run_with_stub(
            [_triple(0.80)], margin=_ACCEPT_MARGIN - 0.0001)
        self.assertEqual(accepted, [])
        self.assertEqual(dropped, 1)

    def test_margin_is_recorded_on_accept(self):
        accepted, _ = _run_with_stub([_triple(0.80)], margin=7.5)
        self.assertAlmostEqual(accepted[0]["verifier_margin"], 7.5)

    def test_accept_margin_is_the_measured_value(self):
        # Deliberately the measured 6.2617, not a rounded 6.3: rounding it
        # changes which triples pass, so a change must be a conscious
        # re-measurement rather than tidying.
        self.assertEqual(_ACCEPT_MARGIN, 6.2617)


class TestFailsClosed(unittest.TestCase):
    """A dead verifier must never let unjudged triples through.

    verify_triples itself raises when the model is gone; the fails-closed
    behaviour lives in the caller (entropy_gate drops the whole band). Both
    sides are pinned here, because a refactor that swallows the exception in
    either place would store facts nobody checked.
    """

    def test_broken_verifier_raises_instead_of_passing(self):
        with self.assertRaises(RuntimeError):
            _run_with_stub(
                [_triple(0.70), _triple(0.80), _triple(0.95)], broken=True)

    def test_broken_verifier_keeps_auto_accepts(self):
        # Above the band the model was never consulted anyway, so a dead
        # model must not block those. Below the band drops regardless.
        # Neither reaches _get_verifier, so neither raises.
        accepted, dropped = _run_with_stub(
            [_triple(0.99), _triple(0.50)], broken=True)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["confidence"], 0.99)
        self.assertEqual(dropped, 1)

    def test_broken_verifier_marks_nothing_judged(self):
        accepted, _ = _run_with_stub([_triple(0.99)], broken=True)
        self.assertIsNone(accepted[0].get("verifier_margin"))

    def test_malformed_confidence_drops(self):
        # A triple whose confidence cannot be read must not sneak into any
        # branch by accident.
        accepted, dropped = _run_with_stub(
            [{"subject": "A", "predicate": "uses", "object": "B",
              "confidence": "high"}], margin=99.0)
        self.assertEqual(accepted, [])
        self.assertEqual(dropped, 1)


class TestBandConstants(unittest.TestCase):
    """The band both sides agree on, pinned in one place."""

    def test_band_is_what_the_decision_record_says(self):
        self.assertEqual((BAND_LO, BAND_HI), (0.70, 0.95))

    def test_verbalise_falls_back_safely_on_unknown_predicate(self):
        from src.extraction.verbalise import verbalise
        claim = verbalise("X", "teleports_into", "Y")
        self.assertIn("X", claim)
        self.assertIn("Y", claim)
        # A de-sugared claim is evidence against acceptance, which is the
        # safe direction: an awkward claim should not read as entailed.
        self.assertIn("teleports into", claim)


if __name__ == "__main__":
    unittest.main()
