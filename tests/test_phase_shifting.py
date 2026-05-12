"""Regression test for phase_shifting.extract_phase.

Builds a 4-step PSI stack from the fixture's analytical phi1 via
synthesize_psi_stack, runs extract_phase, then verifies that
unwrap_2d(extracted) reproduces regression_data['phi1_unwrapped'] to
ATOL_PIPELINE.

The fixture intentionally does not store the wrapped phase directly
(it's an intermediate the notebook discards), so this test exercises
extract_phase via the unwrap step. The chained-pipeline tolerance
(ATOL_PIPELINE = 1e-8) absorbs ULP-scale drift from sin/cos of pi.
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_PIPELINE
from phase_shifting import extract_phase
from synthetic_fringes import synthesize_psi_stack
from unwrapping import unwrap_2d


def test_extract_phase_then_unwrap_matches_fixture(regression_data):
    phi1 = regression_data["phi1"]
    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]

    stack = synthesize_psi_stack(phi1, deltas)
    wrapped = extract_phase(stack, deltas)
    unwrapped = unwrap_2d(wrapped)

    np.testing.assert_allclose(
        unwrapped,
        regression_data["phi1_unwrapped"],
        atol=ATOL_PIPELINE,
        err_msg=(
            "extract_phase + unwrap_2d must reproduce the notebook's "
            "phi1_unwrapped from the analytical phi1"
        ),
    )
