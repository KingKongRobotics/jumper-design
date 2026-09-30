"""Bounded spawn-surface audit, separate from controller/dynamics acceptance."""
from .package_io import PackageError


def check_spawn_surfaces(model, data, scene_geoms, position):
    import mujoco
    import numpy as np

    tolerance = 0.03
    # Sample near the declared floor point, not from above roofs or trees.
    height = 0.25
    robot = [i for i in range(model.ngeom) if i not in scene_geoms
             and int(model.geom_bodyid[i]) != 0
             and (model.geom_contype[i] or model.geom_conaffinity[i])]
    collision = [i for i in scene_geoms if any(
        (int(model.geom_contype[i]) & int(model.geom_conaffinity[j])) or
        (int(model.geom_conaffinity[i]) & int(model.geom_contype[j])) for j in robot)]
    # Only world-fixed geometry qualifies as stationary spawn support.
    collision = [i for i in collision if int(model.body_weldid[int(model.geom_bodyid[i])]) == 0]
    visual = [i for i in scene_geoms if model.geom_rgba[i, 3] > 0
              and (model.geom_matid[i] < 0 or model.mat_rgba[model.geom_matid[i], 3] > 0)]
    groups = model.geom_group.copy()
    rgba = model.geom_rgba.copy()
    materials = model.mat_rgba.copy()
    mask = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)
    direction = np.array([0., 0., -1.])
    samples = []

    def ray(ids, point, include_invisible=False):
        model.geom_group[:] = 1
        model.geom_group[ids] = 0
        model.geom_rgba[:] = rgba
        model.mat_rgba[:] = materials
        if include_invisible:
            model.geom_rgba[:, 3] = 1
            model.mat_rgba[:, 3] = 1
        hit = np.array([-1], dtype=np.int32)
        distance = mujoco.mj_ray(model, data, point, direction, mask, True, -1, hit)
        return (None, None) if distance < 0 else (float(point[2] - distance), int(hit[0]))

    try:
        for dx, dy in ((0, 0), (.05, 0), (-.05, 0), (0, .05), (0, -.05)):
            point = np.array([position[0] + dx, position[1] + dy, position[2] + height])
            support, support_id = ray(collision, point, True)
            visible, visible_id = ray(visual, point)
            if support is None or abs(support - position[2]) > tolerance:
                raise PackageError("spawn support surface missing or differs from declared floor height "
                                   f"at ({point[0]:.3f}, {point[1]:.3f}): support={support}, floor={position[2]}")
            if visible is not None and abs(visible - support) > tolerance:
                name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, visible_id)
                raise PackageError("spawn visual/collision surface mismatch: "
                                   f"{name}, visual_z={visible:.6f}, support_z={support:.6f}")
            samples.append({"xy": point[:2].tolist(), "support_z": support,
                            "visual_z": visible, "support_geom_id": support_id})
    finally:
        model.geom_group[:] = groups
        model.geom_rgba[:] = rgba
        model.mat_rgba[:] = materials
    return {"passed": True, "tolerance_m": tolerance, "samples": samples,
            "scope": "five floor rays within 0.05m of spawn; starts 0.25m above floor",
            "limitations": "Not a full footprint, route, mesh convex-hull or dynamics validation",
            "dynamic_smoke_tested": False}
