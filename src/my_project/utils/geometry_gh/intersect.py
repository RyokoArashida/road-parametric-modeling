from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import Point2D, Point3D, Vector2D
from my_project.utils.geometry_gh.const import (
    const_extended_line_from_two_points,
    const_point_obj,
    const_vertical_line_from_point,
    const_vertical_srf_from_point_and_axis,
    const_vertical_srf_from_two_points,
)


def split_two_surfaces(
    srf_a: Union[rg.Surface, rg.Brep],
    srf_b: Union[rg.Surface, rg.Brep],
    tol: Optional[float] = 0.01,
) -> tuple[list[rg.Brep], list[rg.Brep]]:
    """
    2つのSurface/Brepを、互いをカッターとしてSplitし、
    分割後のBrep群を返す。
    """
    if isinstance(srf_a, rg.Brep):
        brep_a = srf_a
    else:
        brep_a = srf_a.ToBrep()

    if isinstance(srf_b, rg.Brep):
        brep_b = srf_b
    else:
        brep_b = srf_b.ToBrep()

    if brep_a is None:
        raise ValueError("srf_a を Brep に変換できませんでした。")
    if brep_b is None:
        raise ValueError("srf_b を Brep に変換できませんでした。")

    split_a = brep_a.Split(brep_b, tol)
    split_b = brep_b.Split(brep_a, tol)

    pieces_a = list(split_a) if split_a and split_a.Length > 0 else [brep_a]
    pieces_b = list(split_b) if split_b and split_b.Length > 0 else [brep_b]

    return pieces_a, pieces_b


def get_intersect_point_on_curve_with_xy(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    point: Point2D,
    axis_vector: Vector2D, # 断面で考えているときはそれに直交する方向。
)->Point3D:
    planer_srf = const_vertical_srf_from_point_and_axis(point, axis_vector)
    intersection_events = rg.Intersect.Intersection.CurveBrep(curve, planer_srf, 0.01)
    if not intersection_events:
        raise ValueError(f"曲線と平面の交差が見つかりませんでした。point={point}, axis_vector={axis_vector}")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError(f"曲線と平面の交点が見つかりませんでした。point={point}, axis_vector={axis_vector}")
    if len(point) > 1:
        raise ValueError(f"曲線と平面の交点が複数見つかりました。point={point}, axis_vector={axis_vector}")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)

def get_intersect_point_on_srf_with_point(
    srf: Union[rg.Surface, rg.Brep],
    point: Union[Point3D, Point2D, rg.Point3d],
) -> Optional[Point3D]:
    linecrv = const_vertical_line_from_point(point)
    brep_srf = srf if isinstance(srf, rg.Brep) else srf.ToBrep()
    intersection_events = rg.Intersect.Intersection.CurveBrep(linecrv, brep_srf, 0.01)
    if not intersection_events:
        raise ValueError("曲線とサーフェスの交差が見つかりませんでした")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError("曲線とサーフェスの交点が見つかりませんでした")
    if len(point) > 1:
        raise ValueError("曲線とサーフェスの交点が複数見つかりました")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)

def get_intersect_point_on_srf_with_points(
    srf: Union[rg.Surface, rg.Brep],
    points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    linecrv = const_extended_line_from_two_points(*points)
    brep_srf = srf if isinstance(srf, rg.Brep) else srf.ToBrep()
    intersection_events = rg.Intersect.Intersection.CurveBrep(linecrv, brep_srf, 0.01)
    if not intersection_events:
        raise ValueError("曲線とサーフェスの交差が見つかりませんでした")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError("曲線とサーフェスの交点が見つかりませんでした")
    if len(point) > 1:
        raise ValueError("曲線とサーフェスの交点が複数見つかりました")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)


def get_intersect_points_on_brep_with_point(
    brep: rg.Brep,
    intersection_points: Union[Point3D, Point2D, rg.Point3d],
) -> Optional[Point3D]:
    linecrv = const_vertical_line_from_point(intersection_points)
    intersection_events = rg.Intersect.Intersection.CurveBrep(linecrv, brep, 0.01)
    if not intersection_events:
        raise ValueError(f"曲線とブレップの交差が見つかりませんでした。point={intersection_points}")
    intersection_points = intersection_events[2]
    if len(intersection_points) == 0:
        raise ValueError(f"曲線とブレップの交点が見つかりませんでした。point={intersection_points}")
    if len(intersection_points) > 2:
        raise ValueError(f"曲線とブレップの交点が複数見つかりました。point={intersection_points}")
    return intersection_points

def get_intersect_point_on_crvs_with_both_edge_points(
    target_crv_points: list[Union[Point3D, Point2D, rg.Point3d]],
    cutter_crv_points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    planer_srf =const_vertical_srf_from_two_points(
        cutter_crv_points[0],
        cutter_crv_points[1],
    )
    target_crv = const_extended_line_from_two_points(
        target_crv_points[0],
        target_crv_points[1],
    )
    intersection_events = rg.Intersect.Intersection.CurveBrep(target_crv, planer_srf, 0.01)
    if not intersection_events:
        raise ValueError("曲線と平面の交差が見つかりませんでした。")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError("曲線と平面の交点が見つかりませんでした。")
    if len(point) > 1:
        raise ValueError("曲線と平面の交点が複数見つかりました。")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)

def get_intersect_point_on_crvs(
    target_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    cutter_crv_points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    planer_srf =const_vertical_srf_from_two_points(
        cutter_crv_points[0],
        cutter_crv_points[1],
    )
    if isinstance(target_crv, rg.Curve):
        target_curve = target_crv
    elif isinstance(target_crv, rg.Line):
        target_curve = rg.LineCurve(target_crv)
    elif isinstance(target_crv, rg.PolylineCurve):
        target_curve = rg.PolylineCurve(target_crv)
    elif isinstance(target_crv, rg.Circle):
        target_curve = target_crv.ToNurbsCurve()
    else:
        raise ValueError(f"Unsupported object type: {type(target_crv)}")

    intersection_events = rg.Intersect.Intersection.CurveBrep(target_curve, planer_srf, 0.01)
    if not intersection_events:
        raise ValueError("曲線と平面の交差が見つかりませんでした。")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError("曲線と平面の交点が見つかりませんでした。")
    if len(point) > 1:
        raise ValueError("曲線と平面の交点が複数見つかりました。")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)


def trim_curve_between_two_points(
    target_curve: rg.Curve,
    start_point: Union[Point3D, rg.Point3d],
    end_point: Union[Point3D, rg.Point3d],
) -> rg.Curve:
    start_point = const_point_obj(start_point)
    end_point = const_point_obj(end_point)
    ok1, t1 = target_curve.ClosestPoint(start_point)
    ok2, t2 = target_curve.ClosestPoint(end_point)
    if not ok1 or not ok2:
        raise ValueError("ClosestPoint failed.")
    t_start = min(t1, t2)
    t_end = max(t1, t2)
    trimmed = target_curve.Trim(t_start, t_end)
    if trimmed is None:
        raise ValueError("Trim failed.")
    return trimmed