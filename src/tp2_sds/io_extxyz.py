from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Iterator

import numpy as np

PROPERTY_SCHEMA = "id:I:1:type:I:1:pos:R:3:velo:R:3:radius:R:1:color:R:3:vector_color:R:3"
DEFAULT_PBC = (True, True, False)


@dataclass(frozen=True)
class TrajectoryFrame:
    ids: np.ndarray
    types: np.ndarray
    positions: np.ndarray
    velocities: np.ndarray
    radii: np.ndarray
    colors: np.ndarray
    vector_colors: np.ndarray
    time: float
    lattice: tuple[float, float, float, float, float, float, float, float, float]
    pbc: tuple[bool, bool, bool] = DEFAULT_PBC

    def __post_init__(self) -> None:
        particle_count = int(self.ids.shape[0])
        expected_shapes = {
            "types": (particle_count,),
            "positions": (particle_count, 3),
            "velocities": (particle_count, 3),
            "radii": (particle_count,),
            "colors": (particle_count, 3),
            "vector_colors": (particle_count, 3),
        }
        actual_shapes = {
            "types": self.types.shape,
            "positions": self.positions.shape,
            "velocities": self.velocities.shape,
            "radii": self.radii.shape,
            "colors": self.colors.shape,
            "vector_colors": self.vector_colors.shape,
        }
        for name, shape in expected_shapes.items():
            if actual_shapes[name] != shape:
                raise ValueError(f"{name} has shape {actual_shapes[name]} but expected {shape}")


def lattice_for_box(L: float) -> tuple[float, float, float, float, float, float, float, float, float]:
    return (L, 0.0, 0.0, 0.0, L, 0.0, 0.0, 0.0, 1.0)


def write_extxyz(path: Path, frames: list[TrajectoryFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for frame in frames:
            particle_count = int(frame.ids.shape[0])
            handle.write(f"{particle_count}\n")
            handle.write(_build_comment_line(frame))
            handle.write("\n")
            for index in range(particle_count):
                row = [
                    str(int(frame.ids[index])),
                    str(int(frame.types[index])),
                    *(_format_float(value) for value in frame.positions[index]),
                    *(_format_float(value) for value in frame.velocities[index]),
                    _format_float(frame.radii[index]),
                    *(_format_float(value) for value in frame.colors[index]),
                    *(_format_float(value) for value in frame.vector_colors[index]),
                ]
                handle.write(" ".join(row))
                handle.write("\n")


def iter_extxyz(path: Path) -> Iterator[TrajectoryFrame]:
    with path.open("r", encoding="utf-8") as handle:
        while True:
            first_line = handle.readline()
            if not first_line:
                break
            stripped_first_line = first_line.strip()
            if not stripped_first_line:
                continue
            particle_count = int(stripped_first_line)
            comment_line = handle.readline().strip()
            metadata = _parse_comment_line(comment_line)

            ids = np.empty(particle_count, dtype=int)
            types = np.empty(particle_count, dtype=int)
            positions = np.empty((particle_count, 3), dtype=float)
            velocities = np.empty((particle_count, 3), dtype=float)
            radii = np.empty(particle_count, dtype=float)
            colors = np.empty((particle_count, 3), dtype=float)
            vector_colors = np.empty((particle_count, 3), dtype=float)

            for index in range(particle_count):
                parts = handle.readline().split()
                if len(parts) != 15:
                    raise ValueError(f"Expected 15 columns in frame row, found {len(parts)}")
                ids[index] = int(parts[0])
                types[index] = int(parts[1])
                positions[index] = np.asarray(parts[2:5], dtype=float)
                velocities[index] = np.asarray(parts[5:8], dtype=float)
                radii[index] = float(parts[8])
                colors[index] = np.asarray(parts[9:12], dtype=float)
                vector_colors[index] = np.asarray(parts[12:15], dtype=float)

            yield TrajectoryFrame(
                ids=ids,
                types=types,
                positions=positions,
                velocities=velocities,
                radii=radii,
                colors=colors,
                vector_colors=vector_colors,
                time=metadata["time"],
                lattice=metadata["lattice"],
                pbc=metadata["pbc"],
            )


def read_extxyz(path: Path) -> list[TrajectoryFrame]:
    return list(iter_extxyz(path))


def _build_comment_line(frame: TrajectoryFrame) -> str:
    lattice = " ".join(_format_scalar(value) for value in frame.lattice)
    pbc = " ".join("T" if value else "F" for value in frame.pbc)
    time_value = _format_scalar(frame.time)
    return f'Lattice="{lattice}" pbc="{pbc}" Time={time_value} Properties={PROPERTY_SCHEMA}'


def _parse_comment_line(comment_line: str) -> dict[str, object]:
    tokens = shlex.split(comment_line)
    metadata: dict[str, str] = {}
    for token in tokens:
        key, value = token.split("=", 1)
        metadata[key] = value
    if metadata.get("Properties") != PROPERTY_SCHEMA:
        raise ValueError("Unexpected Properties schema in extended XYZ file")
    lattice_values = tuple(float(value) for value in metadata["Lattice"].split())
    if len(lattice_values) != 9:
        raise ValueError("Lattice must contain 9 numeric values")
    pbc_tokens = metadata["pbc"].split()
    if len(pbc_tokens) != 3:
        raise ValueError("pbc must contain 3 flags")
    return {
        "lattice": lattice_values,
        "pbc": tuple(token.upper() == "T" for token in pbc_tokens),
        "time": float(metadata["Time"]),
    }


def _format_float(value: float) -> str:
    return f"{value:.8f}"


def _format_scalar(value: float) -> str:
    return f"{value:g}"

