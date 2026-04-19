from typing import Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)


def const_point_obj(point: Union[Point3D, Point2D, rg.Point3d]) -> rg.Point3d:
    if isinstance(point, Point2D):
        return rg.Point3d(point.x, point.y, 0)
    if isinstance(point, Point3D):
        return rg.Point3d(point.x, point.y, point.z)
    return point


def get_point_dict(point_dict:  dict[str,tuple[float, float, float]]) -> dict[str, rg.Point3d]:
    return {key: rg.Point3d(*coords) for key, coords in point_dict.items()}
