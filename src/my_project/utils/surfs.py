
from typing import Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.points import const_point_obj


def const_surf_obj_from_points(
    points: Union[list[Point3D], list[Point2D]]
) -> rg.Brep:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points + [corner_points[0]])
    curve = rg.PolylineCurve(polyline)
    print(curve)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={corner_points}")
    breps = rg.Brep.CreatePlanarBreps(curve)
    if not breps:
        raise ValueError(
            f"Failed to create planar brep. points={corner_points}"
        )
    return breps[0]
