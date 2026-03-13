from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from tp2_sds.analysis import stationary_window, write_aggregate_csv
from tp2_sds.config import RunSummary


def test_stationary_window_discards_initial_fraction_but_keeps_last_frame() -> None:
    assert stationary_window(1) == (0, 0)
    assert stationary_window(2) == (1, 1)
    assert stationary_window(10) == (3, 9)


def test_write_aggregate_csv_uses_sample_standard_deviation(tmp_path: Path) -> None:
    path = tmp_path / "aggregate.csv"
    summaries = [
        RunSummary(scenario="A", eta=0.1, seed=1, t_start=3, t_end=9, va_mean_stationary=1.0),
        RunSummary(scenario="A", eta=0.1, seed=2, t_start=3, t_end=9, va_mean_stationary=3.0),
    ]

    write_aggregate_csv(path, summaries)

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["scenario"] == "A"
    assert rows[0]["eta"] == "0.100000"
    assert np.isclose(float(rows[0]["va_mean"]), 2.0)
    assert np.isclose(float(rows[0]["va_std"]), np.sqrt(2.0))
