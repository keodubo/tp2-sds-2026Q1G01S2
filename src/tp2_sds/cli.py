from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path
from typing import Sequence

from .analysis import analyze_runs
from .config import DEFAULT_OUTPUTS_ROOT, DEFAULT_RHO, format_eta, make_simulation_config, normalize_scenario
from .simulation import write_simulation_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tp2-sds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate_parser = subparsers.add_parser("simulate", help="Generate one synthetic run")
    _add_simulation_arguments(simulate_parser)
    simulate_parser.set_defaults(handler=_handle_simulate)

    batch_parser = subparsers.add_parser("batch", help="Generate a cartesian product of runs")
    batch_parser.add_argument("--scenarios", required=True, help="Comma-separated scenarios, e.g. A,B,C")
    batch_parser.add_argument("--etas", required=True, help="Comma-separated eta values")
    batch_parser.add_argument("--seeds", required=True, help="Comma-separated seed values")
    _add_common_run_arguments(batch_parser)
    batch_parser.set_defaults(handler=_handle_batch)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze runs already written to disk")
    analyze_parser.add_argument("--runs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    analyze_parser.add_argument("--scenario", help="Optional comma-separated scenario filter")
    analyze_parser.add_argument("--eta", help="Optional comma-separated eta filter")
    analyze_parser.add_argument("--seed", help="Optional comma-separated seed filter")
    analyze_parser.set_defaults(handler=_handle_analyze)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_simulate(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    run_directory = write_simulation_run(config, args.output_root, force=args.force)
    print(run_directory)
    return 0


def _handle_batch(args: argparse.Namespace) -> int:
    scenarios = [normalize_scenario(value) for value in _parse_csv(args.scenarios)]
    etas = [float(value) for value in _parse_csv(args.etas)]
    seeds = [int(value) for value in _parse_csv(args.seeds)]

    created_runs: list[Path] = []
    for scenario, eta, seed in product(scenarios, etas, seeds):
        run_args = argparse.Namespace(**vars(args))
        run_args.scenario = scenario
        run_args.eta = eta
        run_args.seed = seed
        config = _config_from_args(run_args)
        created_runs.append(write_simulation_run(config, args.output_root, force=args.force))

    print(f"Created {len(created_runs)} runs under {args.output_root}")
    return 0


def _handle_analyze(args: argparse.Namespace) -> int:
    summaries = analyze_runs(
        args.runs_root,
        scenario_filter={normalize_scenario(value) for value in _parse_csv(args.scenario)} if args.scenario else None,
        eta_filter={format_eta(float(value)) for value in _parse_csv(args.eta)} if args.eta else None,
        seed_filter={int(value) for value in _parse_csv(args.seed)} if args.seed else None,
    )
    print(f"Analyzed {len(summaries)} runs and wrote {args.runs_root / 'aggregate.csv'}")
    return 0


def _add_simulation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eta", required=True, type=float)
    parser.add_argument("--seed", required=True, type=int)
    _add_common_run_arguments(parser)


def _add_common_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--steps", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    parser.add_argument("--L", type=float, default=10.0)
    parser.add_argument("--rho", type=float)
    parser.add_argument("--N", type=int)
    parser.add_argument("--r", type=float, default=1.0)
    parser.add_argument("--v", type=float, default=0.03)
    parser.add_argument("--dt", type=float, default=1.0)
    parser.add_argument("--force", action="store_true")


def _config_from_args(args: argparse.Namespace):
    rho = args.rho if args.rho is not None else (DEFAULT_RHO if args.N is None else None)
    return make_simulation_config(
        scenario=args.scenario,
        eta=args.eta,
        steps=args.steps,
        seed=args.seed,
        L=args.L,
        rho=rho,
        N=args.N,
        r=args.r,
        v=args.v,
        dt=args.dt,
    )


def _parse_csv(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
