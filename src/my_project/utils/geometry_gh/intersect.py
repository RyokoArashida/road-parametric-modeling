from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import Point2D, Point3D, Vector2D
from my_project.utils.geometry_gh.const import const_srf_from_point_and_axis


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
    planer_srf = const_srf_from_point_and_axis(point, axis_vector)
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
    