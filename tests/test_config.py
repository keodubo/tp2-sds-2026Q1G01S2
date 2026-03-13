from __future__ import annotations

from pathlib import Path

import pytest

from tp2_sds.config import LeaderSpec, SimulationConfig, build_run_directory, make_simulation_config


def test_leader_spec_roundtrip_variants() -> None:
    specs = [
        LeaderSpec.none(),
        LeaderSpec.fixed(theta0=1.25),
        LeaderSpec.circular(center_x=5.0, center_y=5.0, radius=5.0, omega=0.006),
    ]

    for spec in specs:
        assert LeaderSpec.from_dict(spec.to_dict()) == spec


def test_simulation_config_roundtrip_and_path() -> None:
    config = make_simulation_config(scenario="b", eta=0.25, steps=8, seed=3)
    clone = SimulationConfig.from_dict(config.to_dict())

    assert clone == config
    assert build_run_directory(Path("outputs"), "b", 0.25, 3) == Path("outputs/scenario=B/eta=0.250000/seed=3")


def test_make_simulation_config_rejects_inconsistent_density() -> None:
    with pytest.raises(ValueError):
        make_simulation_config(scenario="A", eta=0.1, steps=5, seed=1, L=10.0, rho=4.0, N=12)

