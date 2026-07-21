from typing import Optional, Union

import Rhino.Geometry as rg

from my_project.config.constants import (
    DEFAULT_GEOMETRY_EXTENT,
    DISTANCE_TOL,
    STANDARD_BASE_Z,
)
from my_project.config.util_schemas import Point2D, Point3D, Vector2D
from my_project.utils.geometry.points import get_distance_3D, get_xy_distance_to_segment
from my_project.utils.geometry_gh.attributes import point3d_from_rg
from my_project.utils.geometry_gh.const import (
    const_curve_obj,
    const_extended_line_from_two_points,
    const_point_obj,
    const_vertical_line_from_point,
    const_vertical_srf_from_closed_curve,
    const_vertical_srf_from_point_and_axis,
    const_vertical_srf_from_two_points,
)


def curve_points_are_on_z(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    z: float,
    tol: float = DISTANCE_TOL,
) -> bool:
    curve = const_curve_obj(curve)
    points = [curve.PointAtStart, curve.PointAtEnd]
    ok, polyline = curve.TryGetPolyline()
    if ok:
        points.extend(polyline)
    elif isinstance(curve, rg.PolyCurve):
        for segment in curve.DuplicateSegments():
            points.extend([segment.PointAtStart, segment.PointAtEnd])
    else:
        nurbs_curve = curve.ToNurbsCurve()
        if nurbs_curve is not None:
            points.extend(
                nurbs_curve.Points[i].Location
                for i in range(nurbs_curve.Points.Count)
            )
    return all(abs(point.Z - z) <= tol for point in points)


def get_intersections_with_vertical_plane(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    plane_points: tuple[Point3D, Point3D],
    z: float = STANDARD_BASE_Z,
    cutter_length: float = DEFAULT_GEOMETRY_EXTENT,
) -> list[Point3D]:
    curve = const_curve_obj(curve)
    reference_z = STANDARD_BASE_Z if curve_points_are_on_z(curve, 0) else z
    plane_srf = const_vertical_srf_from_two_points(
        Point3D(plane_points[0].x, plane_points[0].y, reference_z),
        Point3D(plane_points[1].x, plane_points[1].y, reference_z),
        length=cutter_length,
    )
    curve_on_reference_z = curve.DuplicateCurve()
    curve_on_reference_z.Transform(rg.Transform.PlanarProjection(rg.Plane.WorldXY))
    curve_on_reference_z.Transform(rg.Transform.Translation(rg.Vector3d(0, 0, reference_z)))
    intersection_events = rg.Intersect.Intersection.CurveBrep(
        curve_on_reference_z,
        plane_srf,
        DISTANCE_TOL,
    )
    if not intersection_events or len(intersection_events[2]) == 0:
        return []
    return [point3d_from_rg(point, z=reference_z) for point in intersection_events[2]]


def split_curve_by_lines_and_match_endpoints(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    split_line_points: list[tuple[Point3D, Point3D]],
    target_line_points: dict[str, tuple[Point3D, Point3D]],
    expected_count: int,
    cutter_length: float = DEFAULT_GEOMETRY_EXTENT,
) -> list[dict]:
    curve = const_curve_obj(curve)
    curve_on_reference_z = curve.DuplicateCurve()
    curve_on_reference_z.Transform(rg.Transform.PlanarProjection(rg.Plane.WorldXY))
    curve_on_reference_z.Transform(
        rg.Transform.Translation(rg.Vector3d(0, 0, STANDARD_BASE_Z))
    )
    extended_target_line_points = {}
    for key, points in target_line_points.items():
        extended_line = const_extended_line_from_two_points(
            *points,
            length=cutter_length,
        )
        extended_target_line_points[key] = (
            point3d_from_rg(extended_line.PointAtStart),
            point3d_from_rg(extended_line.PointAtEnd),
        )
    split_params = []
    for line_points in split_line_points:
        for point in get_intersections_with_vertical_plane(
            curve,
            line_points,
            cutter_length=cutter_length,
        ):
            ok, t = curve_on_reference_z.ClosestPoint(const_point_obj(point))
            if not ok:
                raise ValueError(f"Failed to get curve parameter at split point: {point}")
            if all(abs(t - existing) > DISTANCE_TOL for existing in split_params):
                split_params.append(t)
    split_params = sorted(split_params)
    expected_split_point_count = expected_count if curve.IsClosed else expected_count - 1
    if len(split_params) != expected_split_point_count:
        raise ValueError(f"Expected {expected_split_point_count} split points, got {len(split_params)}")
    split_curve_items = []
    if curve.IsClosed:
        domain = curve.Domain
        for i, t0 in enumerate(split_params):
            t1 = split_params[(i + 1) % len(split_params)]
            if t0 < t1:
                split_curve = curve.Trim(t0, t1)
            else:
                part1 = curve.Trim(t0, domain.T1)
                part2 = curve.Trim(domain.T0, t1)
                if part1 is None or part2 is None:
                    split_curve = None
                else:
                    split_curve = rg.PolyCurve()
                    split_curve.Append(part1)
                    split_curve.Append(part2)
            if split_curve is None:
                raise ValueError(f"Failed to trim closed curve between parameters: {t0}, {t1}")
            split_curve_items.append(
                {
                    "curve": split_curve,
                    "start": point3d_from_rg(curve.PointAt(t0)),
                    "end": point3d_from_rg(curve.PointAt(t1)),
                }
            )
    else:
        split_curves = curve.Split(split_params)
        if split_curves:
            split_curve_items = [
                {
                    "curve": split_curve,
                    "start": point3d_from_rg(split_curve.PointAtStart),
                    "end": point3d_from_rg(split_curve.PointAtEnd),
                }
                for split_curve in split_curves
            ]
    if not split_curve_items or len(split_curve_items) != expected_count:
        raise ValueError(f"Expected {expected_count} split curves, got {len(split_curve_items)}")
    items = []
    for split_curve_item in split_curve_items:
        split_curve = split_curve_item["curve"]
        start = split_curve_item["start"]
        end = split_curve_item["end"]
        items.append(
            {
                "curve": const_curve_obj(split_curve).DuplicateCurve(),
                "start": start,
                "end": end,
                "start_matches": {
                    key
                    for key, points in extended_target_line_points.items()
                    if get_xy_distance_to_segment(start, points) <= DISTANCE_TOL
                },
                "end_matches": {
                    key
                    for key, points in extended_target_line_points.items()
                    if get_xy_distance_to_segment(end, points) <= DISTANCE_TOL
                },
            }
        )
    return items



def get_nearest_projected_intersection_with_vertical_plane(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    plane_points: tuple[Point3D, Point3D],
    z: float,
    anchor_point: Point3D,
    context: str = "",
) -> Point3D:
    points = get_intersections_with_vertical_plane(curve, plane_points, z=z)
    if not points:
        suffix = f" context={context}" if context else ""
        raise ValueError(
            "Input curve and projected vertical plane do not intersect."
            f"{suffix}"
        )
    return min(points, key=lambda point: get_distance_3D(point, anchor_point))


def get_curve_intersections_with_vertical_plane(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    plane_points: tuple[Point3D, Point3D],
) -> list[Point3D]:
    plane_srf = const_vertical_srf_from_two_points(plane_points[0], plane_points[1])
    intersection_events = rg.Intersect.Intersection.CurveBrep(
        const_curve_obj(curve),
        plane_srf,
        DISTANCE_TOL,
    )
    if not intersection_events or len(intersection_events[2]) == 0:
        return []
    return [point3d_from_rg(point) for point in intersection_events[2]]


def get_polyline_intersections_with_vertical_plane(
    points: list[Point3D],
    plane_points: tuple[Point3D, Point3D],
) -> list[Point3D]:
    if len(points) < 2:
        return []
    curve = rg.PolylineCurve([const_point_obj(point) for point in points])
    plane_srf = const_vertical_srf_from_two_points(plane_points[0], plane_points[1])
    intersection_events = rg.Intersect.Intersection.CurveBrep(
        curve,
        plane_srf,
        DISTANCE_TOL,
    )
    if not intersection_events or len(intersection_events[2]) == 0:
        return []
    return [point3d_from_rg(point) for point in intersection_events[2]]


def get_cut_point_on_polyline_with_vertical_plane(
    points: list[Point3D],
    cutter_points: list[Point3D],
    anchor_point: Point3D,
) -> Point3D:
    curve = rg.PolylineCurve([const_point_obj(point) for point in points])
    cutter_srf = const_vertical_srf_from_two_points(cutter_points[0], cutter_points[1])
    intersection_events = rg.Intersect.Intersection.CurveBrep(curve, cutter_srf, DISTANCE_TOL)
    if not intersection_events or len(intersection_events[2]) == 0:
        raise ValueError("Polyline and vertical cutter do not intersect")
    points_on_curve = [point3d_from_rg(point) for point in intersection_events[2]]
    return min(points_on_curve, key=lambda point: get_distance_3D(point, anchor_point))


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
    point = const_point_obj(point)
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

def get_intersect_point_on_crv_and_points_in_the_same_plane(
    target_crv: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    cutter_points: list[Union[Point3D, Point2D, rg.Point3d]],
) -> Optional[Point3D]:
    cutter_crv = const_extended_line_from_two_points(
        cutter_points[0],
        cutter_points[1],
    )
    return get_intersect_point_on_crvs_in_the_same_plane(target_crv, cutter_crv)

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
    keep: str = "inside",
) -> list[rg.Brep]:
    if keep not in {"inside", "outside"}:
        raise ValueError(f"keep must be 'inside' or 'outside', got {keep}")
    target_brep = target_srf if isinstance(target_srf, rg.Brep) else target_srf.ToBrep()
    cutter_crv = const_curve_obj(cutter_crv)
    cutter_srf = const_vertical_srf_from_closed_curve(cutter_crv)
    split_result = target_brep.Split(cutter_srf, DISTANCE_TOL)
    if not split_result:
        raise ValueError("サーフェスの分割に失敗しました")
    if split_result.Length == 0:
        raise ValueError("サーフェスの分割結果が空でした")
    if split_result.Length == 1:
        raise ValueError("サーフェスの分割結果が1つだけでした。分割されていない可能性があります。")
    cutter_crv_xy = cutter_crv.DuplicateCurve()
    cutter_crv_xy.Transform(rg.Transform.PlanarProjection(rg.Plane.WorldXY))
    kept = []
    for piece in split_result:
        test_point = get_any_interior_point_on_brep_by_mesh(piece)
        test_point_xy = rg.Point3d(test_point.X, test_point.Y, 0)
        containment = cutter_crv_xy.Contains(test_point_xy, rg.Plane.WorldXY, DISTANCE_TOL)
        is_inside = containment == rg.PointContainment.Inside
        if (keep == "inside" and is_inside) or (keep == "outside" and not is_inside):
            kept.append(piece)
    if len(kept) == 0:
        raise ValueError("分割後のサーフェスのうち、切り取るべき部分が見つかりませんでした")
    return kept


def split_brep_by_vertical_srf_from_two_points_keep_near_point(
    target_brep: Union[rg.Surface, rg.Brep],
    cutter_points: list[Union[Point3D, Point2D, rg.Point3d]],
    keep_point: Union[Point3D, Point2D, rg.Point3d],
    cut_point: Union[Point3D, Point2D, rg.Point3d],
    *,
    cap: bool = True,
    tol: float = DISTANCE_TOL,
) -> rg.Brep:
    if len(cutter_points) != 2:
        raise ValueError(f"Need 2 cutter points, got {len(cutter_points)}")

    target_brep = target_brep if isinstance(target_brep, rg.Brep) else target_brep.ToBrep()
    if target_brep is None:
        raise ValueError("target_brep を Brep に変換できませんでした。")

    cutter_srf = const_vertical_srf_from_two_points(
        cutter_points[0],
        cutter_points[1],
    )
    split_result = target_brep.Split(cutter_srf, tol)
    pieces = list(split_result) if split_result and split_result.Length > 0 else [target_brep]

    keep_pt = const_point_obj(keep_point)
    cut_pt = const_point_obj(cut_point)
    candidates = []
    for piece in pieces:
        test_point = get_any_interior_point_on_brep_by_mesh(piece)
        keep_distance = test_point.DistanceTo(keep_pt)
        cut_distance = test_point.DistanceTo(cut_pt)
        if keep_distance <= cut_distance:
            candidates.append((cut_distance - keep_distance, piece))

    if not candidates:
        raise ValueError("分割後のBrepのうち、keep_point側の部分が見つかりませんでした")
    kept_brep = max(candidates, key=lambda item: item[0])[1]
    if cap:
        capped = kept_brep.CapPlanarHoles(tol)
        if capped is None:
            raise ValueError("Failed to cap brep after split")
        kept_brep = capped
    return kept_brep


def split_breps_by_vertical_srf_from_two_points_keep_near_point(
    target_breps: list[Union[rg.Surface, rg.Brep]],
    cutter_points: list[Union[Point3D, Point2D, rg.Point3d]],
    keep_point: Union[Point3D, Point2D, rg.Point3d],
    cut_point: Union[Point3D, Point2D, rg.Point3d],
    *,
    cap: bool = True,
    tol: float = DISTANCE_TOL,
) -> list[rg.Brep]:
    kept = []
    for target_brep in target_breps:
        kept.append(
            split_brep_by_vertical_srf_from_two_points_keep_near_point(
                target_brep=target_brep,
                cutter_points=cutter_points,
                keep_point=keep_point,
                cut_point=cut_point,
                cap=cap,
                tol=tol,
            )
        )
    if not kept:
        raise ValueError("keep_point側に残すBrepが見つかりませんでした")
    return kept
