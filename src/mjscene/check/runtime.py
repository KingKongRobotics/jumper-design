"""Optional dependency: MuJoCo Python bindings.

`mujoco` is used only to validate generated MJCF. Route all imports through
this module so the missing-dependency case has a single implementation.
"""

from __future__ import annotations

__all__ = ["mujoco", "HAVE_MUJOCO", "MUJOCO_ERROR", "MUJOCO_VERSION"]

try:
    import mujoco                                  # type: ignore

    HAVE_MUJOCO = True
    MUJOCO_ERROR: str | None = None
    MUJOCO_VERSION: str | None = getattr(mujoco, "__version__", None)
except Exception as exc:                           # pragma: no cover - env dependent
    mujoco = None                                  # type: ignore
    HAVE_MUJOCO = False
    MUJOCO_ERROR = str(exc)
    MUJOCO_VERSION = None
