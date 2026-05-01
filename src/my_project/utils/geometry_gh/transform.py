from typing import Any, Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    Point2D,
    Point3D,
)
from my_project.utils.geometry.points import offset_point_in_frame
from my_project.utils.geometry_gh.const import const_point_obj


def offset_obj_in_frame(
    obj: Any,
    local_offset: LocalOffset,
    frame_2D: Frame2D,
) -> Any:
    translation_point = offset_point_in_frame(Point3D(0, 0, 0), local_offset, frame_2D)
    translation_vector = rg.Vector3d(translation_point.x, translation_point.y, translation_point.z)
    transform = rg.Transform.Translation(translation_vector)
    new_obj = obj.Duplicate()
    new_obj.Transform(transform)
    return new_obj

def place_obj(
    obj: Union[rg.Brep, rg.Curve, rg.Point3d, Point3D, Point2D],
    local_origin: Point3D,   # ローカルでの基準点
    world_origin: Point3D,   # 絶対座標
    frame_2D: Frame2D,
) -> Union[rg.Brep, rg.Curve, rg.Point3d]:

    # 回転（XYのみ）
    rot = rg.Transform.Identity
    rot.M00 = frame_2D.x_axis.x
    rot.M10 = frame_2D.x_axis.y
    rot.M01 = frame_2D.y_axis.x
    rot.M11 = frame_2D.y_axis.y
    rot.M22 = 1.0
    rot.M33 = 1.0

    # 平行移動
    t1 = rg.Transform.Translation(-local_origin.x, -local_origin.y, -local_origin.z)
    t2 = rg.Transform.Translation(world_origin.x, world_origin.y, world_origin.z)

    xform = t2 * rot * t1

    if isinstance(obj, rg.Brep):
        new_brep = obj.DuplicateBrep()
        new_brep.Transform(xform)
        return new_brep
    elif isinstance(obj, rg.Curve):
        new_crv = obj.DuplicateCurve()
        new_crv.Transform(xform)
        return new_crv
    elif isinstance(obj, (rg.Point3d, Point3D, Point2D)):
        pt = const_point_obj(obj)
        new_pt = rg.Point3d(pt.X, pt.Y, pt.Z)
        new_pt.Transform(xform)
        return new_pt
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")

def move_obj(
    obj: Union[rg.Brep, rg.Curve, rg.Point3d],
    move_vector: rg.Vector3d,
) -> Union[rg.Brep, rg.Curve, rg.Point3d]:
    transform = rg.Transform.Translation(move_vector)
    new_obj = obj.Duplicate()
    new_obj.Transform(transform)
    return new_obj