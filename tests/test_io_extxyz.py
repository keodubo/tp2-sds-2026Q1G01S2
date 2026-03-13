from __future__ import annotations

from pathlib import Path

import numpy as np

from tp2_sds.io_extxyz import PROPERTY_SCHEMA, TrajectoryFrame, lattice_for_box, read_extxyz, write_extxyz


def test_extxyz_roundtrip_preserves_frame_content(tmp_path: Path) -> None:
    frame = TrajectoryFrame(
        ids=np.array([1, 2], dtype=int),
        types=np.array([1, 2], dtype=int),
        positions=np.array([[1.0, 2.0, 0.0], [3.0, 4.0, 0.0]], dtype=float),
        velocities=np.array([[0.1, 0.2, 0.0], [0.3, 0.4, 0.0]], dtype=float),
        radii=np.array([0.25, 0.35], dtype=float),
        colors=np.array([[0.6, 0.6, 0.6], [0.9, 0.2, 0.1]], dtype=float),
        vector_colors=np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float),
        time=4.0,
        lattice=lattice_for_box(10.0),
    )
    trajectory_path = tmp_path / "trajectory.extxyz"

    write_extxyz(trajectory_path, [frame])
    contents = trajectory_path.read_text(encoding="utf-8").splitlines()
    loaded = read_extxyz(trajectory_path)

    assert contents[0] == "2"
    assert f"Properties={PROPERTY_SCHEMA}" in contents[1]
    assert 'Lattice="10 0 0 0 10 0 0 0 1"' in contents[1]
    assert len(loaded) == 1
    np.testing.assert_array_equal(loaded[0].ids, frame.ids)
    np.testing.assert_allclose(loaded[0].positions, frame.positions)
    np.testing.assert_allclose(loaded[0].velocities, frame.velocities)

