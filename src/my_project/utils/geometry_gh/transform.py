import math
from typing import Any, Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    Point2D,
    Point3D,
)
from my_project.utils.geometry.points import offset_point_in_frame
from my_project.utils.geometry_gh.const import const_curve_obj, const_point_obj


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
    obj: Any,
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
    elif isinstance(obj, (rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle, rg.Arc)):
        crv = const_curve_obj(obj)
        new_crv = crv.DuplicateCurve()
        new_crv.Transform(xform)
        return new_crv
    elif isinstance(obj, (rg.Point3d, Point3D, Point2D)):
        pt = const_point_obj(obj)
        new_pt = rg.Point3d(pt.X, pt.Y, pt.Z)
        new_pt.Transform(xform)
        if isinstance(obj, Point2D):
            return Point2D(new_pt.X, new_pt.Y)
        elif isinstance(obj, Point3D):
            return Point3D(new_pt.X, new_pt.Y, new_pt.Z)
        else:
            return new_pt
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")

def unplace_obj(
    obj: Any,
    local_origin: Point3D,
    world_origin: Point3D,
    frame_2D: Frame2D,
) -> Union[rg.Brep, rg.Curve, rg.Point3d]:

    # place_obj と同じ変換を作る
    rot = rg.Transform.Identity
    rot.M00 = frame_2D.x_axis.x
    rot.M10 = frame_2D.x_axis.y
    rot.M01 = frame_2D.y_axis.x
    rot.M11 = frame_2D.y_axis.y
    rot.M22 = 1.0
    rot.M33 = 1.0

    t1 = rg.Transform.Translation(-local_origin.x, -local_origin.y, -local_origin.z)
    t2 = rg.Transform.Translation(world_origin.x, world_origin.y, world_origin.z)

    xform = t2 * rot * t1

    # 逆変換を取得
    success, inverse_xform = xform.TryGetInverse()
    if not success:
        raise ValueError("Transform could not be inverted.")

    if isinstance(obj, rg.Brep):
        new_brep = obj.DuplicateBrep()
        new_brep.Transform(inverse_xform)
        return new_brep

    elif isinstance(obj, (rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle, rg.Arc)):
        crv = const_curve_obj(obj)
        new_crv = crv.DuplicateCurve()
        new_crv.Transform(inverse_xform)
        return new_crv

    elif isinstance(obj, (rg.Point3d, Point3D, Point2D)):
        pt = const_point_obj(obj)
        new_pt = rg.Point3d(pt.X, pt.Y, pt.Z)
        new_pt.Transform(inverse_xform)
        if isinstance(obj, Point2D):
            return Point2D(new_pt.X, new_pt.Y)
        elif isinstance(obj, Point3D):
            return Point3D(new_pt.X, new_pt.Y, new_pt.Z)
        else:
            return new_pt

    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")

def move_obj(
    obj: Any,
    move_vector: rg.Vector3d,
) -> Union[rg.Brep, rg.Curve, rg.Point3d]:
    transform = rg.Transform.Translation(move_vector)
    if isinstance(obj, rg.Brep):
        new_obj = obj.Duplicate()
        new_obj.Transform(transform)
        return new_obj
    elif isinstance(obj, (rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle, rg.Arc)):
        crv = const_curve_obj(obj)
        new_crv = crv.DuplicateCurve()
        new_crv.Transform(transform)
        return new_crv
    elif isinstance(obj, (rg.Point3d, Point3D, Point2D)):
        pt = const_point_obj(obj)
        new_pt = rg.Point3d(pt.X, pt.Y, pt.Z)
        new_pt.Transform(transform)
        if isinstance(obj, Point2D):
            return Point2D(new_pt.X, new_pt.Y)
        elif isinstance(obj, Point3D):
            return Point3D(new_pt.X, new_pt.Y, new_pt.Z)
        else:
            return new_pt
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")

def get_offset_normal_vector_on_plane(
    p1: Union[rg.Point3d, Point3D],
    p2: Union[rg.Point3d, Point3D],
    plane_p3: Union[rg.Point3d, Point3D],
) -> rg.Vector3d:
    if isinstance(p1, Point3D):
        p1 = const_point_obj(p1)
    if isinstance(p2, Point3D):
        p2 = const_point_obj(p2)
    if isinstance(plane_p3, Point3D):
        plane_p3 = const_point_obj(plane_p3)
    # 平面法線
    a = rg.Vector3d(p2 - p1)
    b = rg.Vector3d(plane_p3 - p1)
    normal = rg.Vector3d.CrossProduct(a, b)
    if not normal.Unitize():
        raise ValueError("Plane normal is zero. The plane points may be collinear.")

    # 線分方向
    line_vec = rg.Vector3d(p2 - p1)
    if not line_vec.Unitize():
        raise ValueError("Line segment length is zero.")

    # 平面内で線分に直交する方向
    move_vec = rg.Vector3d.CrossProduct(normal, line_vec)
    if not move_vec.Unitize():
        raise ValueError("Failed to compute perpendicular vector.")
    
    return move_vec, -move_vec

def offset_line_segment_on_plane(
    p1: Union[rg.Point3d, Point3D],
    p2: Union[rg.Point3d, Point3D],
    plane_p3: Union[rg.Point3d, Point3D],
    offset: float,
) -> tuple[rg.Point3d, rg.Point3d]:
    move_vec_pos, move_vec_neg = get_offset_normal_vector_on_plane(p1, p2, plane_p3)
    move_vec_pos = move_vec_pos * offset
    move_vec_neg = move_vec_neg * offset
    return (p1 + move_vec_pos, p2 + move_vec_pos), (p1 + move_vec_neg, p2 + move_vec_neg)

def offset_line_segment_on_plane_and_get_vectors(
    p1: Union[rg.Point3d, Point3D],
    p2: Union[rg.Point3d, Point3D],
    plane_p3: Union[rg.Point3d, Point3D],
    offset: float,
) -> tuple[rg.Point3d, rg.Point3d]:
    move_vec_pos, move_vec_neg = get_offset_normal_vector_on_plane(p1, p2, plane_p3)
    move_vec_pos_with_offset = move_vec_pos * offset
    move_vec_neg_with_offset = move_vec_neg * offset
    return (p1 + move_vec_pos_with_offset, p2 + move_vec_pos_with_offset), (p1 + move_vec_neg_with_offset, p2 + move_vec_neg_with_offset), move_vec_pos, move_vec_neg 


def dms_float_to_decimal_degrees(dms_value: float) -> float:
    """
    84.5742 -> 84度57分42秒 -> 84 + 57/60 + 42/3600
    -84.5742 も対応。
    """
    sign = -1 if dms_value < 0 else 1
    v = abs(dms_value)

    deg = int(v)
    rest = (v - deg) * 100.0

    minute = int(rest)
    sec = (rest - minute) * 100.0

    if minute >= 60:
        raise ValueError(f"分が60以上です: {minute}。入力値 {dms_value} を確認してください。")
    if sec >= 60:
        raise ValueError(f"秒が60以上です: {sec}。入力値 {dms_value} を確認してください。")

    return sign * (deg + minute / 60.0 + sec / 3600.0)


def rotate_point_around_center_xy(
    point: Union[rg.Point3d, Point3D],
    center: Union[rg.Point3d, Point3D],
    angle_deg: float,
) -> Point3D:
    """
    XY平面上で、centerを中心にpointをangle_degだけ回転する。
    正の角度は反時計回り。
    """
    if isinstance(point, Point3D):
        p = const_point_obj(point)
    if isinstance(center, Point3D):
        c = const_point_obj(center)

    xform = rg.Transform.Rotation(
        math.radians(angle_deg),
        rg.Vector3d.ZAxis,
        c,
    )

    p.Transform(xform)

    if isinstance(point, Point3D):
        return Point3D(
            x=p.X,
            y=p.Y,
            z=p.Z,
        )
    else:
        return p
