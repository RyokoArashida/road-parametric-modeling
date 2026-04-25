import math
from typing import Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.geometry_gh.const import (
    const_point_obj,
)


def sort_points_clockwise_from_upper_right(
    points: list[Union[rg.Point3d, Point3D, Point2D]],
    center: Union[rg.Point3d, Point3D, Point2D],
) -> list[rg.Point3d]:
    points = [const_point_obj(p) for p in points]
    center = const_point_obj(center)
    def sort_key(p: rg.Point3d) -> tuple[float, float]:
        dx = p.X - center.X
        dy = p.Y - center.Y

        r2 = dx * dx + dy * dy
        if r2 == 0:
            # 中心点そのものは最後に
            return (float("inf"), 0.0)

        # +Y軸を基準に時計回り（←ここがミソ）
        angle = math.atan2(dx, dy)

        if angle < 0:
            angle += 2 * math.pi

        return (angle, r2)

    return sorted(points, key=sort_key)

def get_distance_along_crv(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    points: list[Union[rg.Point3d, Point3D, Point2D]],
) -> list[float]:
    point_distances = []
    for p in points:
        p_obj = const_point_obj(p)
        t = curve.ClosestPoint(p_obj)[1]
        if t == 0:
            distance = 0
        elif t == len(points) - 1:
            distance = curve.GetLength()
        else:
            split_curves = curve.Split(t)
            start_curve = split_curves[0]
            distance = start_curve.GetLength()
        point_distances.append(distance)
    return point_distances

