"""Validation layer that runs generated MJCF through MuJoCo.

This is the only layer that depends on the optional `mujoco` package. Specs
can still be written and compiled without it, but MJCF checks are unavailable.

    from mjscene.check import check_model, smoke_test, HAVE_MUJOCO
"""

from __future__ import annotations

from .model import ModelCheck, check_model
from .runtime import HAVE_MUJOCO, MUJOCO_ERROR, MUJOCO_VERSION
from .smoke import SmokeResult, smoke_test

__all__ = ["check_model", "ModelCheck", "smoke_test", "SmokeResult",
           "HAVE_MUJOCO", "MUJOCO_ERROR", "MUJOCO_VERSION"]
