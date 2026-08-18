import numpy as np
import pandas as pd

from src.analysis.structural_audit import (
    implicit_weight_audit,
    seasonal_rank_stability,
    spearman_matrix,
    vif_series,
)


def test_spearman_and_vif_identify_redundancy():
    x = np.arange(1, 21, dtype=float)
    df = pd.DataFrame({"walk": x, "road": 2 * x + 1, "river": x[::-1]})
    corr = spearman_matrix(df, ["walk", "road", "river"])
    assert corr.loc["walk", "road"] == 1.0
    vif = vif_series(df, ["walk", "road", "river"])
    assert np.isinf(vif["walk"]) or vif["walk"] > 10


def test_seasonal_rank_change_and_implicit_weights():
    df = pd.DataFrame(
        {
            "id": ["a", "b", "c", "d"],
            "flood": [1, 2, 3, 4],
            "dry": [4, 2, 3, 1],
        }
    )
    corr, change = seasonal_rank_stability(df, "id", "flood", "dry")
    assert corr < 1.0
    assert change.loc["a"] > 0
    implicit, equal_blocks = implicit_weight_audit(
        {"transport": ["a", "b", "c", "d"], "services": ["e", "f"]}
    )
    assert np.isclose(implicit["transport"], 4 / 6)
    assert np.isclose(equal_blocks["transport"], 0.5)
