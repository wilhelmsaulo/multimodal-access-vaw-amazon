import pandas as pd

from scripts.run_e2sfca_coverage_sensitivity import _decay_parameters


def test_decay_parameterization_has_equal_weight_at_threshold():
    threshold = 240.0
    cutoff_weight = 0.1
    beta, sigma = _decay_parameters(threshold, cutoff_weight)

    exponential_weight = pd.Series([-beta * threshold]).map(__import__("math").exp).item()
    gaussian_weight = __import__("math").exp(-0.5 * (threshold / sigma) ** 2)

    assert abs(exponential_weight - cutoff_weight) < 1e-12
    assert abs(gaussian_weight - cutoff_weight) < 1e-12
