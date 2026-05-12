"""Regression test for unwrapping.unwrap_2d.

Round-trip the fixture's already-unwrapped phi1 through rewrap (via
exp/angle) and then back through unwrap_2d. The result must match the
fixture to ATOL_PIPELINE. This exercises unwrap_2d in isolation, without
depending on extract_phase.

No test on unwrap_2d_skimage — it is the documented robust alternative,
not the operational path the fixture was generated with. Stage 5+ work
will compare the two algorithms on noisy data.
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_PIPELINE
from unwrapping import unwrap_2d


def test_unwrap_2d_round_trip_recovers_fixture(regression_data):
    phi1_unwrapped = regression_data["phi1_unwrapped"]

    # Re-wrap into (-pi, pi] via complex exponential, then unwrap again.
    rewrapped = np.angle(np.exp(1j * phi1_unwrapped))
    recovered = unwrap_2d(rewrapped)

    np.testing.assert_allclose(
        recovered,
        phi1_unwrapped,
        atol=ATOL_PIPELINE,
        err_msg="unwrap_2d round-trip (rewrap -> unwrap) must recover the fixture",
    )
