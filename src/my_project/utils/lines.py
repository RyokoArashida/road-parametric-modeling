from typing import Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.points import const_point_obj


def const_line_obj(
    start: Union[Point3D, Point2D],
    end: Union[Point3D, Point2D],
) -> rg.Line:
    return rg.Line(const_point_obj(start), const_point_obj(end))

def conset_closed_polycurve_obj(
    points: Union[list[Point3D], list[Point2D], list[rg.Point3d]]
) -> rg.PolylineCurve:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points + [corner_points[0]])
    curve = rg.PolylineCurve(polyline)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={corner_points}")
    return curve