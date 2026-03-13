from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_OUTPUTS_ROOT = Path("outputs")
DEFAULT_L = 10.0
DEFAULT_RHO = 4.0
DEFAULT_R = 1.0
DEFAULT_V = 0.03
DEFAULT_DT = 1.0
VALID_SCENARIOS = {"A", "B", "C"}


@dataclass(frozen=True)
class LeaderSpec:
    mode: str
    theta0: float | None = None
    center_x: float | None = None
    center_y: float | None = None
    radius: float | None = None
    omega: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"none", "fixed", "circular"}:
            raise ValueError(f"Unsupported leader mode: {self.mode}")
        if self.mode == "fixed" and self.theta0 is None:
            raise ValueError("fixed leader requires theta0")
        if self.mode == "circular":
            required = (self.center_x, self.center_y, self.radius, self.omega)
            if any(value is None for value in required):
                raise ValueError("circular leader requires center_x, center_y, radius and omega")

    @classmethod
    def none(cls) -> "LeaderSpec":
        return cls(mode="none")

    @classmethod
    def fixed(cls, theta0: float) -> "LeaderSpec":
        return cls(mode="fixed", theta0=float(theta0))

    @classmethod
    def circular(
        cls,
        center_x: float,
        center_y: float,
        radius: float,
        omega: float,
    ) -> "LeaderSpec":
        return cls(
            mode="circular",
            center_x=float(center_x),
            center_y=float(center_y),
            radius=float(radius),
            omega=float(omega),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": self.mode}
        if self.mode == "fixed":
            payload["theta0"] = self.theta0
        if self.mode == "circular":
            payload.update(
                {
                    "center_x": self.center_x,
                    "center_y": self.center_y,
                    "radius": self.radius,
                    "omega": self.omega,
                }
            )
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LeaderSpec":
        mode = str(payload["mode"])
        if mode == "none":
            return cls.none()
        if mode == "fixed":
            return cls.fixed(theta0=float(payload["theta0"]))
        if mode == "circular":
            return cls.circular(
                center_x=float(payload["center_x"]),
                center_y=float(payload["center_y"]),
                radius=float(payload["radius"]),
                omega=float(payload["omega"]),
            )
        raise ValueError(f"Unsupported leader mode: {mode}")


@dataclass(frozen=True)
class SimulationConfig:
    L: float
    rho: float
    N: int
    r: float
    v: float
    dt: float
    eta: float
    steps: int
    seed: int
    scenario: str
    leader_spec: LeaderSpec

    def __post_init__(self) -> None:
        if self.scenario not in VALID_SCENARIOS:
            raise ValueError(f"Unsupported scenario: {self.scenario}")
        if self.L <= 0 or self.rho <= 0 or self.N <= 0 or self.r <= 0 or self.v <= 0 or self.dt <= 0:
            raise ValueError("L, rho, N, r, v and dt must be positive")
        if self.steps <= 0:
            raise ValueError("steps must be positive")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "L": self.L,
            "rho": self.rho,
            "N": self.N,
            "r": self.r,
            "v": self.v,
            "dt": self.dt,
            "eta": self.eta,
            "steps": self.steps,
            "seed": self.seed,
            "scenario": self.scenario,
            "leader_spec": self.leader_spec.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SimulationConfig":
        return cls(
            L=float(payload["L"]),
            rho=float(payload["rho"]),
            N=int(payload["N"]),
            r=float(payload["r"]),
            v=float(payload["v"]),
            dt=float(payload["dt"]),
            eta=float(payload["eta"]),
            steps=int(payload["steps"]),
            seed=int(payload["seed"]),
            scenario=str(payload["scenario"]),
            leader_spec=LeaderSpec.from_dict(payload["leader_spec"]),
        )


@dataclass(frozen=True)
class RunSummary:
    scenario: str
    eta: float
    seed: int
    t_start: int
    t_end: int
    va_mean_stationary: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "eta": self.eta,
            "seed": self.seed,
            "t_start": self.t_start,
            "t_end": self.t_end,
            "va_mean_stationary": self.va_mean_stationary,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunSummary":
        return cls(
            scenario=str(payload["scenario"]),
            eta=float(payload["eta"]),
            seed=int(payload["seed"]),
            t_start=int(payload["t_start"]),
            t_end=int(payload["t_end"]),
            va_mean_stationary=float(payload["va_mean_stationary"]),
        )


def format_eta(eta: float) -> str:
    return f"{eta:.6f}"


def build_run_directory(root: Path, scenario: str, eta: float, seed: int) -> Path:
    scenario_name = normalize_scenario(scenario)
    return root / f"scenario={scenario_name}" / f"eta={format_eta(eta)}" / f"seed={seed}"


def normalize_scenario(scenario: str) -> str:
    normalized = scenario.strip().upper()
    if normalized not in VALID_SCENARIOS:
        raise ValueError(f"Unsupported scenario: {scenario}")
    return normalized


def default_leader_spec(scenario: str, seed: int, L: float, v: float) -> LeaderSpec:
    normalized = normalize_scenario(scenario)
    if normalized == "A":
        return LeaderSpec.none()
    if normalized == "B":
        rng = np.random.default_rng(seed + 10_001)
        return LeaderSpec.fixed(theta0=float(rng.uniform(0.0, 2.0 * np.pi)))
    radius = min(5.0, L / 2.0)
    if radius <= 0.0:
        raise ValueError("circular leader requires a positive radius")
    return LeaderSpec.circular(center_x=L / 2.0, center_y=L / 2.0, radius=radius, omega=v / radius)


def make_simulation_config(
    *,
    scenario: str,
    eta: float,
    steps: int,
    seed: int,
    L: float = DEFAULT_L,
    rho: float | None = DEFAULT_RHO,
    N: int | None = None,
    r: float = DEFAULT_R,
    v: float = DEFAULT_V,
    dt: float = DEFAULT_DT,
    leader_spec: LeaderSpec | None = None,
) -> SimulationConfig:
    normalized_scenario = normalize_scenario(scenario)
    if N is None and rho is None:
        raise ValueError("Either N or rho must be provided")
    if N is None:
        inferred_n = float(rho) * L * L
        rounded_n = round(inferred_n)
        if not np.isclose(inferred_n, rounded_n):
            raise ValueError("rho * L^2 must be an integer if N is omitted")
        N = int(rounded_n)
    if rho is None:
        rho = N / (L * L)
    inferred_rho = N / (L * L)
    if not np.isclose(inferred_rho, rho):
        raise ValueError(f"Inconsistent N and rho for L={L}: expected rho={inferred_rho}")
    if leader_spec is None:
        leader_spec = default_leader_spec(normalized_scenario, seed, L, v)
    return SimulationConfig(
        L=float(L),
        rho=float(rho),
        N=int(N),
        r=float(r),
        v=float(v),
        dt=float(dt),
        eta=float(eta),
        steps=int(steps),
        seed=int(seed),
        scenario=normalized_scenario,
        leader_spec=leader_spec,
    )

