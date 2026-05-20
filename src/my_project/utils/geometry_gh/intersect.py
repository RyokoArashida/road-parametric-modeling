from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import Point2D, Point3D, Vector2D
from my_project.utils.geometry_gh.const import (
    const_curve_obj,
    const_extended_line_from_two_points,
    const_point_obj,
    const_vertical_line_from_point,
    const_vertical_srf_from_closed_curve,
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
    curve = const_curve_obj(curve)
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

def get_closest_point_on_srf_with_point(
    srf: Union[rg.Surface, rg.Brep],
    point: Union[Point3D, Point2D, rg.Point3d],
) -> Optional[Point3D]:
    linecrv = const_vertical_line_from_point(point)
    brep_srf = srf if isinstance(srf, rg.Brep) else srf.ToBrep()
    success, _, pt_on_brep, _ = linecrv.ClosestPoints([brep_srf])
    if not success:
        raise ValueError("ClosestPoints failed.")
    return Point3D(x=pt_on_brep.X, y=pt_on_brep.Y, z=pt_on_brep.Z)



def get_intersect_point_on_srf_with_curve(
    srf: Union[rg.Surface, rg.Brep],
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
) -> Optional[Point3D]:
    brep_srf = srf if isinstance(srf, rg.Brep) else srf.ToBrep()
    curve = const_curve_obj(curve)
    intersection_events = rg.Intersect.Intersection.CurveBrep(curve, brep_srf, 0.01)
    if not intersection_events:
        raise ValueError("曲線とサーフェスの交差が見つかりませんでした")
    point = intersection_events[2]
    if len(point) == 0:
        raise ValueError("曲線とサーフェスの交点が見つかりませんでした")
    if len(point) > 1:
        print(f"曲線とサーフェスの交点が複数見つかりました。point={point}")
        raise ValueError("曲線とサーフェスの交点が複数見つかりました")
    intersect_pt = point[0]
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)

def get_intersect_point_on_srf_with_points(
    srf: Union[rg.Surface, rg.Brep],
    points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    linecrv = const_extended_line_from_two_points(*points)
    return get_intersect_point_on_srf_with_curve(srf, linecrv)


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
        raise ValueError(f"曲線とブレップの交点が3個以上複数見つかりました。point={intersection_points}")
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
    return get_intersect_point_on_srf_with_curve(planer_srf, target_crv)

def get_intersect_point_on_crvs(
    target_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    cutter_crv_points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    planer_srf =const_vertical_srf_from_two_points(
        cutter_crv_points[0],
        cutter_crv_points[1],
    )
    target_crv = const_curve_obj(target_crv)
    return get_intersect_point_on_srf_with_curve(planer_srf, target_crv)

def get_intersect_point_on_crvs_in_the_same_plane(
    target_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    cutter_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
) -> Optional[Point3D]:
    target_crv = const_curve_obj(target_crv)
    cutter_crv = const_curve_obj(cutter_crv)
    intersection_events = rg.Intersect.Intersection.CurveCurve(target_crv, cutter_crv, 0.01, 0.01)
    if not intersection_events:
        raise ValueError("曲線同士の交差が見つかりませんでした")
    if len(intersection_events) == 0:
        raise ValueError("曲線同士の交点が見つかりませんでした")
    if len(intersection_events) > 1:
        raise ValueError("曲線同士の交点が複数見つかりました")
    intersect_pt = intersection_events[0].PointA
    return Point3D(x=intersect_pt.X, y=intersect_pt.Y, z=intersect_pt.Z)

def get_intersect_crv_on_srfs(
    srf_a: Union[rg.Surface, rg.Brep],
    srf_b: Union[rg.Surface, rg.Brep],
    tol: Optional[float] = 0.01,
) -> Optional[rg.Curve]:
    brep_a = srf_a if isinstance(srf_a, rg.Brep) else srf_a.ToBrep()
    brep_b = srf_b if isinstance(srf_b, rg.Brep) else srf_b.ToBrep()
    intersection_events = rg.Intersect.Intersection.BrepBrep(brep_a, brep_b, tol)
    if not intersection_events[0]:
        raise ValueError("サーフェス同士の交差が見つかりませんでした")
    intersection_crvs = intersection_events[1]
    print(intersection_crvs, len(intersection_crvs))
    if len(intersection_crvs) == 0:
        raise ValueError("サーフェス同士の交線が見つかりませんでした")
    return  intersection_crvs

def get_intersect_crv_on_srfs_with_cutter_points(
    target_srf: Union[rg.Surface, rg.Brep],
    cutter_crv_points: list[Union[Point3D, Point2D, rg.Point3d]],
    tol: Optional[float] = 0.01,
) -> Optional[rg.Curve]:
    planer_srf =const_vertical_srf_from_two_points(
        cutter_crv_points[0],
        cutter_crv_points[1],
    )
    return get_intersect_crv_on_srfs(target_srf, planer_srf, tol)



def trim_curve_between_two_points(
    target_curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    start_point: Union[Point3D, rg.Point3d],
    end_point: Union[Point3D, rg.Point3d],
) -> rg.Curve:
    target_curve = const_curve_obj(target_curve)
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

def get_any_interior_point_on_brep_by_mesh(
    brep: rg.Brep,
) -> rg.Point3d:
    """
    Brepをメッシュ化し、メッシュ面の中心からBrepFace内部点を探す。
    細いSplit片ではUVグリッドサンプリングより安定しやすい。
    """
    meshes = rg.Mesh.CreateFromBrep(
        brep,
        rg.MeshingParameters.Default
    )
    if not meshes:
        raise ValueError("Mesh could not be created from brep.")
    for mesh in meshes:
        for mf in mesh.Faces:
            if mf.IsTriangle:
                p0 = mesh.Vertices[mf.A]
                p1 = mesh.Vertices[mf.B]
                p2 = mesh.Vertices[mf.C]
                center = rg.Point3d(
                    (p0.X + p1.X + p2.X) / 3.0,
                    (p0.Y + p1.Y + p2.Y) / 3.0,
                    (p0.Z + p1.Z + p2.Z) / 3.0,
                )
            else:
                p0 = mesh.Vertices[mf.A]
                p1 = mesh.Vertices[mf.B]
                p2 = mesh.Vertices[mf.C]
                p3 = mesh.Vertices[mf.D]
                center = rg.Point3d(
                    (p0.X + p1.X + p2.X + p3.X) / 4.0,
                    (p0.Y + p1.Y + p2.Y + p3.Y) / 4.0,
                    (p0.Z + p1.Z + p2.Z + p3.Z) / 4.0,
                )
            # 念のため、その点がBrep面上のInteriorか確認
            for face in brep.Faces:
                rc, u, v = face.ClosestPoint(center)
                if not rc:
                    continue
                relation = face.IsPointOnFace(u, v)
                if relation == rg.PointFaceRelation.Interior:
                    return face.PointAt(u, v)
    raise ValueError("No interior point found on brep by mesh.")


def trim_srf_by_closed_curve(
    target_srf: Union[rg.Surface, rg.Brep],
    cutter_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
) -> list[rg.Brep]:
    target_brep = target_srf if isinstance(target_srf, rg.Brep) else target_srf.ToBrep()
    cutter_crv = const_curve_obj(cutter_crv)
    cutter_srf = const_vertical_srf_from_closed_curve(cutter_crv)
    split_result = target_brep.Split(cutter_srf, 0.01)
    if not split_result:
        raise ValueError("サーフェスの分割に失敗しました")
    if split_result.Length == 0:
        raise ValueError("サーフェスの分割結果が空でした")
    if split_result.Length == 1:
        raise ValueError("サーフェスの分割結果が1つだけでした。分割されていない可能性があります。")
    kept = []
    for piece in split_result:
        test_point = get_any_interior_point_on_brep_by_mesh(piece)
        containment = cutter_crv.Contains(test_point)
        if containment == rg.PointContainment.Inside:
            kept.append(piece)
    if len(kept) == 0:
        raise ValueError("分割後のサーフェスのうち、切り取るべき部分が見つかりませんでした")
    return kept
