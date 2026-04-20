import math
from typing import Any, Optional, Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    Point2D,
    Point3D,
)
from my_project.utils.points import const_point_obj


# 2つのPointの中点を求める
def midpoint(p1: Union[Point3D, Point2D], p2: Union[Point3D, Point2D]) -> Union[Point3D, Point2D]:
    if isinstance(p1, Point2D) and isinstance(p2, Point2D):
        return Point2D(x=(p1.x + p2.x) / 2, y=(p1.y + p2.y) / 2)
    elif isinstance(p1, Point3D) and isinstance(p2, Point3D):
        return Point3D(x=(p1.x + p2.x) / 2, y=(p1.y + p2.y) / 2, z=(p1.z + p2.z) / 2)
    else:
        raise ValueError("Points must be of the same type")

def offset_point_in_frame(
    point: Union[Point3D, Point2D, rg.Point3d],
    local_offset: LocalOffset,
    frame_2D: Frame2D,
) -> Union[Point3D, Point2D]:
    """pointをframe_2Dのローカル座標系でlocal_offset分だけ移動させる"""
    offset_x = local_offset.x * frame_2D.x_axis.x + local_offset.y * frame_2D.y_axis.x
    offset_y = local_offset.x * frame_2D.x_axis.y + local_offset.y * frame_2D.y_axis.y
    point = const_point_obj(point)
    if isinstance(point, Point2D):
        return Point2D(
            x = point.X + offset_x,
            y = point.Y + offset_y,
        )
    return Point3D(
        x = point.X + offset_x,
        y = point.Y + offset_y,
        z = point.Z + local_offset.z,
    )

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

def extrude_curve(
    obj: Any,
    vector: rg.Vector3d,
    cap: bool = True,
    tol: float = 0.01,
) -> Any:
    if isinstance(obj, rg.Curve):
        curve = obj
    elif isinstance(obj, rg.Line):
        curve = rg.LineCurve(obj)
    elif isinstance(obj, rg.PolylineCurve):
        curve = rg.PolylineCurve(obj)
    elif isinstance(obj, rg.Circle):
        curve = obj.ToNurbsCurve()
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")
    srf = rg.Surface.CreateExtrusion(curve, vector)
    if srf is None:
            raise ValueError("Surface.CreateExtrusion failed")
    brep = srf.ToBrep()
    if brep is None:
        raise ValueError("ToBrep failed")
    if cap:
        capped = brep.CapPlanarHoles(tol)
        if capped is not None:
            brep = capped
    return brep

def extrude_curve_in_frame(
    obj: Any,
    local_offset: LocalOffset,
    frame_2D: Frame2D,
    cap: bool = True,
    tol: float = 0.01,
) -> Any:
    if isinstance(obj, rg.Curve):
        curve = obj
    elif isinstance(obj, rg.Line):
        curve = rg.LineCurve(obj)
    elif isinstance(obj, rg.PolylineCurve):
        curve = rg.PolylineCurve(obj)
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")
    extrusion_point = offset_point_in_frame(Point3D(0, 0, 0), local_offset, frame_2D)
    extrusion_vector = rg.Vector3d(extrusion_point.x, extrusion_point.y, extrusion_point.z)
    srf = rg.Surface.CreateExtrusion(curve, extrusion_vector)
    if srf is None:
            raise ValueError("Surface.CreateExtrusion failed")
    brep = srf.ToBrep()
    if brep is None:
        raise ValueError("ToBrep failed")
    if cap:
        capped = brep.CapPlanarHoles(tol)
        if capped is not None:
            brep = capped
    return brep

def get_plane_from_points(
    p1: Union[Point3D, Point2D, rg.Point3d],
    p2: Union[Point3D, Point2D, rg.Point3d],
    p3: Union[Point3D, Point2D, rg.Point3d],
) -> rg.Plane:
    plane = rg.Plane(const_point_obj(p1), const_point_obj(p2), const_point_obj(p3))
    return plane

def get_slope_plane(
    point: Union[Point3D, Point2D, rg.Point3d],
    slope: float, #%
    XY: str, # Xが増えるとZが増えるのか、Yが増えるとZが増えるのか
) -> rg.Plane:
    if isinstance(point, Point2D):
        base_point = rg.Point3d(point.x, point.y, 0)
    elif isinstance(point, Point3D):
        base_point = rg.Point3d(point.x, point.y, point.z)
    elif isinstance(point, rg.Point3d):
        base_point = point
    p1 = base_point
    if XY == "X":
        p2 = rg.Point3d(base_point.X + 100, base_point.Y, base_point.Z + slope)
        p3 = rg.Point3d(base_point.X, base_point.Y + 100, base_point.Z)
    elif XY == "Y":
        p2 = rg.Point3d(base_point.X, base_point.Y + 100, base_point.Z + slope)
        p3 = rg.Point3d(base_point.X + 100, base_point.Y, base_point.Z)
    else:
        raise ValueError(f"Invalid XY value: {XY}")
    plane = rg.Plane(p1, p2, p3)
    return plane

def make_large_plane_brep(plane: rg.Plane, size: float = 100000.0) -> rg.Brep:
    interval = rg.Interval(-size, size)
    srf = rg.PlaneSurface(plane, interval, interval)
    return srf.ToBrep()

def get_brep_centroid_for_sort(brep: rg.Brep) -> rg.Point3d:
    """
    Z比較用の代表点を返す
    まず体積重心、だめなら面積重心、最後にBBox中心
    """
    if brep.IsSolid:
        vmp = rg.VolumeMassProperties.Compute(brep)
        if vmp is not None:
            return vmp.Centroid

    amp = rg.AreaMassProperties.Compute(brep)
    if amp is not None:
        return amp.Centroid

    return brep.GetBoundingBox(True).Center

def split_brep_and_keep_by_centroid_z(
    brep: rg.Brep,
    cutter: Union[rg.Brep, rg.Plane],
    keep: str = "upper",   # "upper" or "lower"
    tol: float = 0.01,
) -> rg.Brep:
    """
    brepをplaneでsplitし、断片の重心Zを比較して
    upper: Z最大だけ残す
    lower: Z最小だけ残す
    """
    if isinstance(cutter, rg.Plane):
        cutter = make_large_plane_brep(cutter)
    
    print("brep:", brep, type(brep))
    print("cutter:", cutter, type(cutter))

    pieces = brep.Split(cutter, tol)
    pieces = [brep.CapPlanarHoles(tol) or brep for brep in pieces]  # 穴埋めしておく

    if not pieces:
        return None

    if len(pieces) == 1:
        return pieces[0]

    indexed = []
    for i, piece in enumerate(pieces):
        c = get_brep_centroid_for_sort(piece)
        indexed.append((i, piece, c.Z))

    if keep == "upper":
        return max(indexed, key=lambda x: x[2])[1]
    elif keep == "lower":
        return min(indexed, key=lambda x: x[2])[1]
    else:
        raise ValueError(f"Invalid keep value: {keep}")


def get_intersection_polylines(
    brep: rg.Brep,
    cutter: Union[rg.Brep,rg.Plane],
    tol: float = 0.01,
) -> list[rg.Point3d]:
    """
    brep と cutter の交線のうち、
    polyline化できたものだけを点列として返す
    """
    if isinstance(cutter, rg.Plane):
        cutter = make_large_plane_brep(cutter)
    success, curves, points = rg.Intersect.Intersection.BrepBrep(brep, cutter, tol)
    if not success:
        return []
    if len(curves) == 0:
        raise ValueError("No intersection curves found")
    if len(curves) > 1:
        raise ValueError(f"Unexpected multiple intersection curves: {len(curves)}")
    crv = curves[0]
    ok, polyline = crv.TryGetPolyline()
    if ok:
        pts = list(polyline)
        if len(pts) > 1 and pts[0].DistanceTo(pts[-1]) < tol:
                pts = pts[:-1]  # 閉じている場合は最後の点を削除
        return pts
    else:
        raise ValueError("Intersection curve is not a polyline")




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

def get_polyline_crv_from_points(points: list[Union[Point3D, Point2D, rg.Point3d]]) -> rg.PolylineCurve:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 2:
        raise ValueError(f"Need at least 2 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points)
    return rg.PolylineCurve(polyline)

def get_planer_srf_from_points(points: list[Union[Point3D, Point2D, rg.Point3d]]) -> rg.Brep:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points + [corner_points[0]])
    curve = rg.PolylineCurve(polyline)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={corner_points}")
    breps = rg.Brep.CreatePlanarBreps(curve)
    if not breps:
        raise ValueError(
            f"Failed to create planar brep. points={corner_points}"
        )
    return breps[0]

def get_srf_with_loft(curves: list[Union[rg.Curve, rg.Line, rg.PolylineCurve]]) -> rg.Brep:
    if len(curves) < 2:
        raise ValueError(f"Need at least 2 curves to loft, got {len(curves)}")
    loft_type = rg.LoftType.Normal
    lofted = rg.Brep.CreateFromLoft(curves, rg.Point3d.Unset, rg.Point3d.Unset, loft_type, False)
    if not lofted or len(lofted) == 0:
        raise ValueError("Loft failed")
    return lofted[0]


def get_arc_half_from_center_edge_points(
    center: Union[Point3D, Point2D, rg.Point3d],
    edge: Union[Point3D, Point2D, rg.Point3d],
    tangent_dir: str, # "Xplus", "Xminus", "Yplus", "Yminus"のいずれか edgeが中心から見てどの方向にあるか
) -> Optional[rg.ArcCurve]:
    center_pt = const_point_obj(center)
    edge_pt = const_point_obj(edge)
    if tangent_dir == "Xplus":
        tangent = rg.Vector3d(1, 0, 0)
    elif tangent_dir == "Xminus":
        tangent = rg.Vector3d(-1, 0, 0)
    elif tangent_dir == "Yplus":
        tangent = rg.Vector3d(0, 1, 0)
    elif tangent_dir == "Yminus":
        tangent = rg.Vector3d(0, -1, 0)
    else:
        raise ValueError(f"Invalid tangent_dir: {tangent_dir}")
    arc = rg.Arc(center_pt, tangent, edge_pt)
    arc_crv = rg.ArcCurve(arc)
    return arc_crv

def get_arc_from_three_points(
    start: Union[Point3D, Point2D, rg.Point3d],
    mid: Union[Point3D, Point2D, rg.Point3d],
    end: Union[Point3D, Point2D, rg.Point3d],
) -> Optional[rg.ArcCurve]:
    start_pt = const_point_obj(start)
    mid_pt = const_point_obj(mid)
    end_pt = const_point_obj(end)
    arc = rg.Arc(start_pt, mid_pt, end_pt)
    arc_crv = rg.ArcCurve(arc)
    return arc_crv

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


