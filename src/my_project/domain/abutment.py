from my_project.config.constants import DISTANCE_TOL
from my_project.config.util_schemas import Point3D
from my_project.utils.geometry.points import get_distance_3D


def get_corner_point(corners, key: str):
    if isinstance(corners, dict):
        return corners[key]
    return getattr(corners, key)


def get_abut_wing_named_points(wing_dict: dict) -> dict[str, Point3D]:
    U_base = get_corner_point(wing_dict["U_wing_top_points"], "DT")
    D_base = get_corner_point(wing_dict["D_wing_top_points"], "UT")
    U_wing = get_corner_point(wing_dict["U_wing_top_points"], "DN")
    D_wing = get_corner_point(wing_dict["D_wing_top_points"], "UN")
    candidates = [
        get_corner_point(wing_dict["U_wing_top_points"], key)
        for key in ["DT", "DN", "UN", "UT"]
    ] + [
        get_corner_point(wing_dict["D_wing_top_points"], key)
        for key in ["DT", "DN", "UN", "UT"]
    ]

    base_center = Point3D(
        x=(U_base.x + D_base.x) / 2,
        y=(U_base.y + D_base.y) / 2,
        z=(U_base.z + D_base.z) / 2,
    )
    wing_center = Point3D(
        x=(U_wing.x + D_wing.x) / 2,
        y=(U_wing.y + D_wing.y) / 2,
        z=(U_wing.z + D_wing.z) / 2,
    )

    unique_candidates = []
    for point in candidates:
        if all(get_distance_3D(point, existing) > DISTANCE_TOL for existing in unique_candidates):
            unique_candidates.append(point)
    sorted_by_base_to_wing = sorted(
        unique_candidates,
        key=lambda point: (
            (point.x - base_center.x) * (wing_center.x - base_center.x)
            + (point.y - base_center.y) * (wing_center.y - base_center.y)
        ),
    )
    bridge_points = sorted_by_base_to_wing[:2]
    soil_points = sorted_by_base_to_wing[-2:]

    def split_UD(points: list[Point3D]) -> tuple[Point3D, Point3D]:
        sorted_by_U_to_D = sorted(
            points,
            key=lambda point: (
                (point.x - U_base.x) * (D_base.x - U_base.x)
                + (point.y - U_base.y) * (D_base.y - U_base.y)
            ),
        )
        return sorted_by_U_to_D[0], sorted_by_U_to_D[1]

    U_bridge, D_bridge = split_UD(bridge_points)
    U_soil, D_soil = split_UD(soil_points)
    return {
        "U_bridge": U_bridge,
        "D_bridge": D_bridge,
        "U_soil": U_soil,
        "D_soil": D_soil,
    }
