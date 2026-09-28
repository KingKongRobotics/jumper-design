"""Simulation smoke test: a model that compiles may still fail to run.

Run for several seconds and report steady penetration, peak and final speeds,
contact count, NaNs, and MuJoCo mjWARN_* warnings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .runtime import HAVE_MUJOCO, MUJOCO_ERROR, mujoco

__all__ = ["SmokeResult", "smoke_test"]


@dataclass
class SmokeResult:
    ok: bool
    sim_time: float = 0.0
    wall_time: float = 0.0
    realtime_factor: float = 0.0
    warnings: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    max_penetration: float = 0.0      # transient, dominated by the initial drop
    steady_penetration: float = 0.0   # measured over the last 40% of the run
    max_speed: float = 0.0            # linear, m/s
    final_speed: float = 0.0
    final_spin: float = 0.0           # rad/s
    max_contacts: int = 0
    settled: bool = False

    def report(self) -> str:
        lines = [f"Simulation smoke test: {self.sim_time:.2f}s simulated / {self.wall_time:.2f}s wall time "
                 f"({self.realtime_factor:.1f}x real time)",
                 f"  Maximum contacts {self.max_contacts}, steady penetration {self.steady_penetration * 1000:.2f} mm "
                 f"(impact peak {self.max_penetration * 1000:.1f} mm), peak linear speed {self.max_speed:.2f} m/s, "
                 f"final {self.final_speed:.3f} m/s / {self.final_spin:.2f} rad/s"
                 f"{' (settled)' if self.settled else ''}"]
        for w in self.warnings:
            lines.append(f"  [MuJoCo warning] {w}")
        for p in self.problems:
            lines.append(f"  [problem] {p}")
        return "\n".join(lines)


def smoke_test(xml_path: Path | str, duration: float = 3.0,
               settle_threshold: float = 0.02) -> SmokeResult:
    """Step the scene and look for the failure modes generated scenes actually hit."""
    import time

    if not HAVE_MUJOCO:
        return SmokeResult(ok=False, problems=[f"The mujoco Python package is not installed ({MUJOCO_ERROR})"])
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    res = SmokeResult(ok=True)
    steps = max(1, int(duration / model.opt.timestep))
    steady_from = int(steps * 0.6)

    def velocities() -> tuple[float, float]:
        """Max linear (m/s) and angular (rad/s) speed over all bodies."""
        if model.nbody <= 1:
            return 0.0, 0.0
        cvel = data.cvel[1:]                      # skip world body; [ang(3), lin(3)]
        lin = max(math.sqrt(float(v[3] ** 2 + v[4] ** 2 + v[5] ** 2)) for v in cvel)
        ang = max(math.sqrt(float(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)) for v in cvel)
        return lin, ang

    t0 = time.perf_counter()
    for step in range(steps):
        try:
            mujoco.mj_step(model, data)
        except Exception as exc:
            # mujoco.FatalError (arena/stack exhausted, contact buffer overflow…)
            # aborts the run; report it instead of crashing the caller.
            res.ok = False
            res.problems.append(
                f"MuJoCo raised {type(exc).__name__} at t={data.time:.3f}s: {exc}"
                " (common causes: <size memory=...> too small or excessive contacts)")
            break
        res.max_contacts = max(res.max_contacts, int(data.ncon))
        if data.ncon:
            pen = -min(0.0, float(min(data.contact.dist[:data.ncon])))
            res.max_penetration = max(res.max_penetration, pen)
            if step >= steady_from:
                res.steady_penetration = max(res.steady_penetration, pen)
        lin, _ = velocities()
        res.max_speed = max(res.max_speed, lin)
        if not all(math.isfinite(q) for q in data.qpos):
            res.ok = False
            res.problems.append(f"qpos contains NaN/Inf at t={data.time:.3f}s; the simulation diverged")
            break
    res.wall_time = time.perf_counter() - t0
    res.sim_time = float(data.time)
    res.realtime_factor = res.sim_time / res.wall_time if res.wall_time > 0 else 0.0
    res.final_speed, res.final_spin = velocities()
    res.settled = res.final_speed < settle_threshold and res.final_spin < 0.5

    for i in range(len(data.warning)):
        n = int(data.warning[i].number)
        if n:
            try:
                label = mujoco.mjtWarning(i).name
            except Exception:
                label = f"warning[{i}]"
            res.warnings.append(f"{label} x{n}")
            if label in ("mjWARN_BADQPOS", "mjWARN_BADQVEL", "mjWARN_BADQACC",
                         "mjWARN_BADCTRL"):
                res.ok = False
                res.problems.append(f"{label}: invalid state, often caused by penetration, zero mass, or a large timestep")
            if label == "mjWARN_CONTACTFULL":
                res.problems.append("Contact count exceeds the limit; reduce scattered objects or increase nconmax")

    if res.steady_penetration > 0.005:
        res.problems.append(
            f"Steady penetration of {res.steady_penetration * 1000:.1f} mm is excessive: "
            "set defaults.contact to 'rigid', reduce timestep, or increase impratio")
    if res.max_speed > 50:
        res.problems.append(f"Linear speed reached {res.max_speed:.0f} m/s; objects may overlap initially")
    if model.nv and res.final_speed > 1.0:
        res.problems.append(
            f"Still moving at {res.final_speed:.2f} m/s after {duration}s: "
            "an object may be jittering, rolling continuously, or falling out of the scene; expected slopes or rolling objects may explain this")
    return res
