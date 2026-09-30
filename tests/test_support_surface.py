import numpy as np
import pytest

from shellflow.package_io import PackageError
from shellflow.support_surface import check_spawn_surfaces


def model_for(ground=True, road=None, road_collision=False, invisible=False, floor=0):
    mj = pytest.importorskip("mujoco")
    geoms = f'<geom name="floor" type="plane" pos="0 0 {floor}" size="2 2 .1"/>' if ground else ''
    if road is not None:
        geoms += f'<geom name="road" type="box" pos="0 0 {road-.01}" size="1 1 .01" contype="{int(road_collision)}" conaffinity="{int(road_collision)}" rgba="1 1 1 {0 if invisible else 1}"/>'
    m = mj.MjModel.from_xml_string('<mujoco><worldbody>' + geoms + '<body pos="0 0 .4"><freejoint/><geom type="sphere" size=".02" mass="1"/></body></worldbody></mujoco>')
    d = mj.MjData(m)
    mj.mj_forward(m,d)
    ids = set(range(m.ngeom-1))
    return m,d,ids


def test_rejects_raised_visual_road_and_restores_model():
    m,d,ids = model_for(road=.1118)
    groups, rgba = m.geom_group.copy(),m.geom_rgba.copy()
    with pytest.raises(PackageError, match="visual/collision surface mismatch"):
        check_spawn_surfaces(m,d,ids,[0,0,0])
    assert np.array_equal(groups,m.geom_group)
    assert np.array_equal(rgba,m.geom_rgba)


def test_accepts_aligned_raised_road():
    m,d,ids = model_for(road=.11,road_collision=True)
    assert check_spawn_surfaces(m,d,ids,[0,0,.11])["passed"]


def test_invisible_collision_surface_counts_as_support():
    m,d,ids = model_for(ground=False,road=0,road_collision=True,invisible=True)
    assert check_spawn_surfaces(m,d,ids,[0,0,0])["passed"]


def test_rejects_missing_support():
    m,d,ids = model_for(ground=False,road=.1)
    with pytest.raises(PackageError,match="support surface missing"):
        check_spawn_surfaces(m,d,ids,[0,0,0])


def test_rejects_wrong_spawn_height():
    m,d,ids = model_for()
    with pytest.raises(PackageError,match="declared floor height"):
        check_spawn_surfaces(m,d,ids,[0,0,.1])


def test_small_decorative_offset_is_allowed():
    m,d,ids = model_for(road=.002)
    report=check_spawn_surfaces(m,d,ids,[0,0,0])
    assert report["passed"] and not report["dynamic_smoke_tested"]
