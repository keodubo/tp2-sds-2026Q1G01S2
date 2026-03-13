from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path
from typing import Sequence

from .analysis import DEFAULT_TRANSIENT_FRACTION, analyze_runs
from .config import DEFAULT_OUTPUTS_ROOT, DEFAULT_RHO, format_eta, make_simulation_config, normalize_scenario
from .reporting import CampaignSpec, default_campaign_spec, generate_results, run_campaign
from .simulation import write_simulation_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tp2-sds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate_parser = subparsers.add_parser("simulate", help="Generate one simulation run")
    _add_simulation_arguments(simulate_parser)
    simulate_parser.set_defaults(handler=_handle_simulate)

    batch_parser = subparsers.add_parser("batch", help="Generate a cartesian product of runs")
    batch_parser.add_argument("--scenarios", required=True, help="Comma-separated scenarios, e.g. A,B,C")
    batch_parser.add_argument("--etas", required=True, help="Comma-separated eta values")
    batch_parser.add_argument("--seeds", required=True, help="Comma-separated seed values")
    batch_parser.add_argument("--skip-existing", action="store_true")
    _add_common_run_arguments(batch_parser)
    batch_parser.set_defaults(handler=_handle_batch)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze runs already written to disk")
    analyze_parser.add_argument("--runs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    analyze_parser.add_argument("--scenario", help="Optional comma-separated scenario filter")
    analyze_parser.add_argument("--eta", help="Optional comma-separated eta filter")
    analyze_parser.add_argument("--seed", help="Optional comma-separated seed filter")
    analyze_parser.add_argument("--transient-fraction", type=float, default=DEFAULT_TRANSIENT_FRACTION)
    analyze_parser.set_defaults(handler=_handle_analyze)

    campaign_parser = subparsers.add_parser("campaign", help="Run a batch campaign, analyze it, and generate figures")
    campaign_parser.add_argument("--runs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    campaign_parser.add_argument("--scenarios", help="Comma-separated scenarios, defaults to A,B,C")
    campaign_parser.add_argument("--etas", help="Comma-separated eta values, defaults to 0.0..5.0 step 0.5")
    campaign_parser.add_argument("--seeds", help="Comma-separated seed values, defaults to 1,2,3,4,5")
    campaign_parser.add_argument("--steps", type=int)
    campaign_parser.add_argument("--transient-fraction", type=float, default=DEFAULT_TRANSIENT_FRACTION)
    campaign_parser.add_argument("--skip-existing", action="store_true")
    _add_physics_arguments(campaign_parser)
    campaign_parser.set_defaults(handler=_handle_campaign)

    plot_parser = subparsers.add_parser("plot", help="Generate figures and demo manifest from existing runs")
    plot_parser.add_argument("--runs-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    plot_parser.add_argument("--scenario", help="Optional comma-separated scenario filter")
    plot_parser.add_argument("--eta", help="Optional comma-separated eta filter")
    plot_parser.add_argument("--seed", help="Optional comma-separated seed filter")
    plot_parser.add_argument("--transient-fraction", type=float, default=DEFAULT_TRANSIENT_FRACTION)
    plot_parser.set_defaults(handler=_handle_plot)
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
    skipped_runs = 0
    for scenario, eta, seed in product(scenarios, etas, seeds):
        run_args = argparse.Namespace(**vars(args))
        run_args.scenario = scenario
        run_args.eta = eta
        run_args.seed = seed
        config = _config_from_args(run_args)
        run_directory = args.output_root / f"scenario={scenario}" / f"eta={format_eta(eta)}" / f"seed={seed}"
        if args.skip_existing and _run_is_complete(run_directory):
            skipped_runs += 1
            continue
        created_runs.append(write_simulation_run(config, args.output_root, force=args.force))

    print(f"Created {len(created_runs)} runs under {args.output_root} (skipped {skipped_runs})")
    return 0


def _handle_analyze(args: argparse.Namespace) -> int:
    summaries = analyze_runs(
        args.runs_root,
        scenario_filter={normalize_scenario(value) for value in _parse_csv(args.scenario)} if args.scenario else None,
        eta_filter={format_eta(float(value)) for value in _parse_csv(args.eta)} if args.eta else None,
        seed_filter={int(value) for value in _parse_csv(args.seed)} if args.seed else None,
        transient_fraction=args.transient_fraction,
    )
    print(f"Analyzed {len(summaries)} runs and wrote {args.runs_root / 'aggregate.csv'}")
    return 0


def _handle_campaign(args: argparse.Namespace) -> int:
    default_spec = default_campaign_spec(runs_root=args.runs_root)
    spec = CampaignSpec(
        scenarios=tuple(normalize_scenario(value) for value in _parse_csv(args.scenarios)) if args.scenarios else default_spec.scenarios,
        etas=tuple(float(value) for value in _parse_csv(args.etas)) if args.etas else default_spec.etas,
        seeds=tuple(int(value) for value in _parse_csv(args.seeds)) if args.seeds else default_spec.seeds,
        steps=args.steps if args.steps is not None else default_spec.steps,
        transient_fraction=args.transient_fraction,
        runs_root=args.runs_root,
    )
    result = run_campaign(
        spec,
        skip_existing=args.skip_existing,
        L=args.L,
        rho=args.rho if args.rho is not None else (DEFAULT_RHO if args.N is None else None),
        N=args.N,
        r=args.r,
        v=args.v,
        dt=args.dt,
    )
    print(
        f"Campaign completed: created {result.created_runs}, skipped {result.skipped_runs}, "
        f"analyzed {result.analyzed_runs}, results in {result.results_directory}"
    )
    return 0


def _handle_plot(args: argparse.Namespace) -> int:
    scenario_filter = {normalize_scenario(value) for value in _parse_csv(args.scenario)} if args.scenario else None
    eta_filter = {format_eta(float(value)) for value in _parse_csv(args.eta)} if args.eta else None
    seed_filter = {int(value) for value in _parse_csv(args.seed)} if args.seed else None
    summaries = analyze_runs(
        args.runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
        transient_fraction=args.transient_fraction,
    )
    results_directory = generate_results(
        args.runs_root,
        scenario_filter=scenario_filter,
        eta_filter=eta_filter,
        seed_filter=seed_filter,
    )
    print(f"Generated {len(summaries)} summaries and wrote results to {results_directory}")
    return 0


def _add_simulation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eta", required=True, type=float)
    parser.add_argument("--seed", required=True, type=int)
    _add_common_run_arguments(parser)


def _add_common_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--steps", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUTS_ROOT)
    _add_physics_arguments(parser)
    parser.add_argument("--force", action="store_true")


def _add_physics_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--L", type=float, default=10.0)
    parser.add_argument("--rho", type=float)
    parser.add_argument("--N", type=int)
    parser.add_argument("--r", type=float, default=1.0)
    parser.add_argument("--v", type=float, default=0.03)
    parser.add_argument("--dt", type=float, default=1.0)


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


def _run_is_complete(run_directory: Path) -> bool:
    return (run_directory / "run.json").exists() and (run_directory / "trajectory.extxyz").exists()


if __name__ == "__main__":
    raise SystemExit(main())
