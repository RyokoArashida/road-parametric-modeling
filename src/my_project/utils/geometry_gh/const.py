from __future__ import annotations

from typing import Any, Optional, Union

from Rhino import Geometry as rg

from my_project.config.constants import STANDARD_BASE_Z, EPS
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
    Square_Corners,
    Vector2D,
)

def const_point_obj(point: Union[Point3D, Point2D, rg.Point3d]) -> rg.Point3d:
    if isinstance(point, Point2D):
        return rg.Point3d(point.x, point.y, 0)
    if isinstance(point, Point3D):
        return rg.Point3d(point.x, point.y, point.z)
    return point

def const_3Dpoint(point:Union[Point3D, Point2D, rg.Point3d]) -> Point3D:
    if isinstance(point, Point3D):
        return point
    if isinstance(point, Point2D):
        return Point3D(x=point.x, y=point.y, z=0)
    return Point3D(x=point.X, y=point.Y, z=point.Z)

def const_curve_obj(
    crv: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle, rg.Arc]
) -> rg.Curve:
    if isinstance(crv, rg.Curve):
        curve = crv
    elif isinstance(crv, rg.Line):
        curve = rg.LineCurve(crv)
    elif isinstance(crv, rg.PolylineCurve):
        curve = rg.PolylineCurve(crv)
    elif isinstance(crv, rg.Arc):
        curve = rg.ArcCurve(crv)
    elif isinstance(crv, rg.Circle):
        curve = crv.ToNurbsCurve()
    else:
        raise ValueError(f"Unsupported object type: {type(crv)}")
    if curve is None:
        raise ValueError("Failed to create curve object")
    return curve


def const_line_obj(
    start: Union[Point3D, Point2D, rg.Point3d],
    end: Union[Point3D, Point2D, rg.Point3d],
) -> rg.Line:
    return rg.Line(const_point_obj(start), const_point_obj(end))

def remove_same_points(points: list[Union[Point3D, Point2D, rg.Point3d]], tol: float = 0.01) -> list[Union[Point3D, Point2D, rg.Point3d]]:
    unique_points = []
    for point in points:
        if point is None:
            continue
        if all(const_point_obj(point).DistanceTo(const_point_obj(existing)) > tol for existing in unique_points):
            unique_points.append(const_point_obj(point))
    return unique_points

def const_polycurve_obj(points: list[Union[Point3D, Point2D, rg.Point3d]]) -> rg.PolylineCurve:
    unique_points = remove_same_points(points)
    if len(unique_points) < 2:
        raise ValueError(f"Need at least 2 valid points, got {len(unique_points)}")
    polyline = rg.Polyline(unique_points)
    return rg.PolylineCurve(polyline)

def const_closed_polycurve_obj(
    points: Union[list[Point3D], list[Point2D], list[rg.Point3d]]
) -> rg.PolylineCurve:
    unique_points = remove_same_points(points)
    if len(unique_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(unique_points)}")
    polyline = rg.Polyline(unique_points + [unique_points[0]])
    curve = rg.PolylineCurve(polyline)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={unique_points}")
    return curve

def const_planer_srf_obj_from_points(
    points: Union[list[Point3D], list[Point2D]]
) -> rg.Brep:
    curve = const_closed_polycurve_obj(points)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={points}")
    breps = rg.Brep.CreatePlanarBreps(curve)
    if not breps:
        raise ValueError(
            f"Failed to create planar brep. points={points}"
        )
    return breps[0]

    

def const_extrude_brep_from_curve(
    crv: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    vector: rg.Vector3d,
    cap: bool = True,
    tol: float = 0.01,
) -> Any:
    curve = const_curve_obj(crv)
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

def const_brep_from_two_closed_point_lists(
    points1: list[Union[Point3D, Point2D, rg.Point3d]],
    points2: list[Union[Point3D, Point2D, rg.Point3d]],
    cap: bool = True,
    tol: float = 0.01,
) -> rg.Brep:
    if len(points1) != len(points2):
        raise ValueError(f"Point list lengths must match, got {len(points1)} and {len(points2)}")
    if len(points1) < 3:
        raise ValueError(f"Need at least 3 points, got {len(points1)}")
    brep = const_srf_from_2crvs([
        const_closed_polycurve_obj(points1),
        const_closed_polycurve_obj(points2),
    ])
    if cap:
        capped = brep.CapPlanarHoles(tol)
        if capped is not None:
            brep = capped
    return brep

def const_brep_to_z_from_points(
    points: list[Union[Point3D, Point2D, rg.Point3d]],
    target_z: float,
    cap: bool = True,
    tol: float = 0.01,
) -> rg.Brep:
    top_points = [const_3Dpoint(point) for point in points]
    bottom_points = [
        Point3D(x=point.x, y=point.y, z=target_z)
        for point in top_points
    ]
    return const_brep_from_two_closed_point_lists(
        top_points,
        bottom_points,
        cap=cap,
        tol=tol,
    )

def const_closed_polycurve_from_square_corners(
    corners: Square_Corners,
) -> rg.PolylineCurve:
    return const_closed_polycurve_obj([corners.DT, corners.DN, corners.UN, corners.UT])

def const_z_extruded_box_from_4points(
    points: list[Union[Point3D, Point2D, rg.Point3d]],
    z_offset: float,
    cap: bool = True,
    tol: float = 0.01,
) -> rg.Brep:
    unique_points = remove_same_points(points, tol=tol)
    if len(unique_points) != 4:
        raise ValueError(f"Need 4 valid points, got {len(unique_points)}")
    if z_offset == 0:
        raise ValueError("z_offset must not be 0")
    moved_points = []
    for point in unique_points:
        point = const_point_obj(point)
        moved_points.append(rg.Point3d(point.X, point.Y, point.Z + z_offset))
    return const_brep_from_two_closed_point_lists(
        unique_points,
        moved_points,
        cap=cap,
        tol=tol,
    )

def const_z_extruded_brep_from_srf(
    brep: rg.Brep,
    z_offset: float,
    cap: bool = True,
    tol: float = 0.01,
) -> rg.Brep:
    vector = rg.Vector3d(0, 0, float(z_offset))
    bottom = brep.DuplicateBrep()
    top = brep.DuplicateBrep()
    top.Transform(rg.Transform.Translation(vector))

    side_breps = []
    for edge_crv in bottom.DuplicateNakedEdgeCurves(True, True):
        top_edge_crv = edge_crv.DuplicateCurve()
        top_edge_crv.Transform(rg.Transform.Translation(vector))
        side_breps.append(const_srf_from_2crvs([edge_crv, top_edge_crv]))

    joined = join_breps_or_raise(
        [bottom, top] + side_breps,
        tol=tol,
        context="const_z_extruded_brep_from_srf",
    )
    if cap:
        capped = joined.CapPlanarHoles(tol)
        if capped is not None:
            joined = capped
    return joined

def const_brep_from_point_lists(
    point_lists: list[list[Union[Point3D, Point2D, rg.Point3d]]],
    cap: bool = True,
    tol: float = 0.01,
) -> rg.Brep:
    if len(point_lists) < 2:
        raise ValueError(f"Need at least 2 point lists, got {len(point_lists)}")
    lengths = {len(point_list) for point_list in point_lists}
    if len(lengths) != 1:
        raise ValueError(f"Point lists must have the same length, got {sorted(lengths)}")
    if next(iter(lengths)) < 2:
        raise ValueError("Each point list must have at least 2 points")
    crvs = [
        const_polycurve_obj(points)
        for points in zip(*point_lists)
    ]
    return const_brep_from_all_crvs(crvs, cap=cap, tol=tol)

def boolean_difference_or_raise(
    base_brep: rg.Brep,
    cutter_brep: rg.Brep,
    context: str = "",
    tol: float = 0.01,
) -> rg.Brep:
    diff = rg.Brep.CreateBooleanDifference(base_brep, cutter_brep, tol)
    if not diff or len(diff) == 0:
        suffix = f" ({context})" if context else ""
        raise ValueError(f"Failed to subtract brep{suffix}")
    if len(diff) == 1:
        return diff[0]
    return join_breps_or_raise(list(diff), tol=tol, context=context)

def const_planer_srf_from_points(points: list[Union[Point3D, Point2D, rg.Point3d]]) -> rg.Brep:
    unique_points = remove_same_points(points)
    if len(unique_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(unique_points)}")
    polyline = rg.Polyline(unique_points + [unique_points[0]])
    curve = rg.PolylineCurve(polyline)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={unique_points}")
    breps = rg.Brep.CreatePlanarBreps(curve)
    if not breps:
        raise ValueError(
            f"Failed to create planar brep. points={unique_points}"
        )
    return breps[0]

def const_srf_from_2crvs(curves: list[Union[rg.Curve, rg.Line, rg.PolylineCurve]]) -> rg.Brep:
    if len(curves) != 2:
        raise ValueError(f"Need 2 curves, got {len(curves)}")
    curves = [const_curve_obj(crv) for crv in curves]
    srf = rg.NurbsSurface.CreateRuledSurface(curves[0], curves[1])
    if srf is not None:
        return srf.ToBrep()

    lofts = rg.Brep.CreateFromLoft(
        curves,
        rg.Point3d.Unset,
        rg.Point3d.Unset,
        rg.LoftType.Normal,
        False,
    )
    if not lofts or len(lofts) == 0:
        raise ValueError("Failed to create ruled or loft surface")
    return lofts[0]


def join_breps_or_raise(
    breps: list[rg.Brep],
    tol: float = 0.01,
    context: str = "",
) -> rg.Brep:
    joined = rg.Brep.JoinBreps(breps, tol)
    if not joined or len(joined) == 0:
        suffix = f" ({context})" if context else ""
        raise ValueError(f"Failed to join breps{suffix}. count={len(breps)}, tol={tol}")
    return joined[0]

def const_arc_half_from_center_edge_points(
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

def const_arc_from_three_points(
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

def side_of_point(p0, p1, p):
    v = p1 - p0
    w = p - p0
    cross = rg.Vector3d.CrossProduct(v, w)
    z = cross.Z
    if z > EPS:
        return "left"
    elif z < -EPS:
        return "right"
    else:
        return "on"

def const_arc_from_p0_p1_radius(
    p0: Union[Point3D, Point2D, rg.Point3d],
    p1: Union[Point3D, Point2D, rg.Point3d],
    R: float,
    direction: str, # "left" or "right" p0からp1に向かうベクトルから見て、円弧の中心がどちら側にあるか
) -> Optional[rg.ArcCurve]:
    p0 = const_point_obj(p0)
    p1 = const_point_obj(p1)
    harf_distance = p0.DistanceTo(p1) / 2
    mid_pt_R = (2*R**2 -2*R*(R**2 - harf_distance**2)**0.5)**0.5 # p0とp1から等距離で、かつ半径Rの円弧上にある点までの距離
    p0_circle = rg.Circle(p0, mid_pt_R)
    p1_circle = rg.Circle(p1, mid_pt_R)
    intersect_event = rg.Intersect.Intersection.CircleCircle(p0_circle, p1_circle)
    ip0 = intersect_event[1]
    ip1 = intersect_event[2]
    if ip0 is None or ip1 is None:
        raise ValueError(f"Failed to find intersection point of circles. p0={p0}, p1={p1}, R={R}")
    ip0_dir = side_of_point(p0, p1, ip0)
    left_ip = ip0 if ip0_dir == "left" else ip1
    right_ip = ip0 if ip0_dir == "right" else ip1
    if direction == "left":
        arc = rg.Arc(p0, left_ip, p1)
    elif direction == "right":
        arc = rg.Arc(p0, right_ip, p1)
    else:
        raise ValueError(f"Invalid direction: {direction}")
    arc_crv = rg.ArcCurve(arc)
    return arc_crv

# そのポイントを通り、与えた軸に沿った、かつ垂直な直線を作る
def const_vertical_line_from_point(
    point: Union[Point3D, rg.Point3d],
    height: float = 500000, # 500m
) -> rg.LineCurve:
    point = const_point_obj(point)
    if STANDARD_BASE_Z-height/2 > point.Z or point.Z > STANDARD_BASE_Z+height/2:
        point = rg.Point3d(point.X, point.Y, STANDARD_BASE_Z)
    top = rg.Point3d(point.X, point.Y, point.Z + height / 2)
    bottom = rg.Point3d(point.X, point.Y, point.Z - height / 2)
    line = rg.Line(bottom, top)
    return rg.LineCurve(line)

# そのポイントを通り、与えた軸に沿った、かつ垂直な平面のサーフェスを作る
def const_vertical_srf_from_point_and_axis(
    point: Union[Point3D, rg.Point3d],
    axis_vector: Vector2D,
    height: float = 500000, # 500m
    length: float = 100000, # 100m
) -> rg.Brep:
    point = const_point_obj(point)
    plus_pt = rg.Point3d(
        point.X + axis_vector.x * length / 2,
        point.Y + axis_vector.y * length / 2,
        point.Z
    )
    minus_pt = rg.Point3d(
        point.X - axis_vector.x * length / 2,
        point.Y - axis_vector.y * length / 2,
        point.Z
    )
    plus_line = const_vertical_line_from_point(plus_pt, height)
    minus_line = const_vertical_line_from_point(minus_pt, height)
    srf = const_srf_from_2crvs([rg.LineCurve(plus_line), rg.LineCurve(minus_line)])
    return srf

# 2つの点を通る長い直線をつくる
def const_extended_line_from_two_points(
    point1: Union[Point2D, Point3D, rg.Point3d],
    point2: Union[Point2D, Point3D, rg.Point3d],
    length: float = 100000, # 100m
) -> rg.LineCurve:
    point1 = const_point_obj(point1)
    point2 = const_point_obj(point2)
    mid_pt = rg.Point3d(
        (point1.X + point2.X) / 2,
        (point1.Y + point2.Y) / 2,
        (point1.Z + point2.Z) / 2,
    )
    dir_vector = rg.Vector3d(
        point2.X - point1.X,
        point2.Y - point1.Y,
        point2.Z - point1.Z,
    )
    dir_vector.Unitize()
    dir_vector *= length / 2
    plus_pt = mid_pt + dir_vector
    minus_pt = mid_pt - dir_vector
    line = rg.Line(minus_pt, plus_pt)
    return rg.LineCurve(line)

# 2つの点を通り、垂直な平面のサーフェスを作る
def const_vertical_srf_from_two_points(
    point1: Union[Point3D, rg.Point3d],
    point2: Union[Point3D, rg.Point3d],
    height: float = 100000, # 100m
    length: float = 100000, # 100m
) -> rg.Brep:
    point1 = const_point_obj(point1)
    point2 = const_point_obj(point2)
    mid_pt = rg.Point3d(
        (point1.X + point2.X) / 2,
        (point1.Y + point2.Y) / 2,
        (point1.Z + point2.Z) / 2,
    )
    axis_vector = rg.Vector3d(point2.X - point1.X, point2.Y - point1.Y, 0)
    axis_vector.Unitize()
    axis_vector = Vector2D(x=axis_vector.X, y=axis_vector.Y)
    srf = const_vertical_srf_from_point_and_axis(mid_pt, axis_vector, height=height, length=length)
    return srf

def const_vertical_srf_from_closed_curve(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    height: float = 100000, # 100m
) -> rg.Brep:
    curve = const_curve_obj(curve)
    if not curve.IsClosed:
        raise ValueError("Curve must be closed")
    minus_transform = rg.Transform.Translation(rg.Vector3d(0, 0, -height / 2))
    plus_transform = rg.Transform.Translation(rg.Vector3d(0, 0, height / 2))
    bottom_crv = curve.Duplicate()
    top_crv = curve.Duplicate()
    bottom_crv.Transform(minus_transform)
    top_crv.Transform(plus_transform)
    srf = const_srf_from_2crvs([bottom_crv, top_crv])
    return srf

def const_point_along_curve(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle], 
    base_point: Union[Point3D, rg.Point3d], 
    offset: float
) -> rg.Point3d:
    base_point = const_point_obj(base_point)
    curve = const_curve_obj(curve)
    ok, t0 = curve.ClosestPoint(base_point)
    if not ok:
        raise ValueError("ClosestPoint failed")

    # base_ptまでの弧長
    length0 = curve.GetLength(rg.Interval(curve.Domain.Min, t0))

    # 進みたい位置の弧長
    target_length = length0 + offset

    # 弧長 → parameter に変換
    ok, t = curve.LengthParameter(target_length)
    if not ok:
        raise ValueError("LengthParameter failed (out of range?)")
    return curve.PointAt(t)

def get_normal_vector_on_curve_2d(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    point: Union[Point3D, rg.Point3d],
) -> tuple[rg.Vector3d, rg.Vector3d]:
    """
    crv上のpointにおける接線に対して、
    XY平面上の右側・左側単位ベクトルを返す。

    前提:
    - crvは下側を始点、上側を終点とする向き
    - XY平面上で処理する
    """
    curve = const_curve_obj(curve)
    point = const_point_obj(point)
    success, t = curve.ClosestPoint(point)
    if not success:
        raise ValueError("point is not near the curve.")
    tangent = curve.TangentAt(t)
    # XY成分だけ使う
    tangent.Z = 0
    if not tangent.Unitize():
        raise ValueError("tangent vector is zero.")
    right = rg.Vector3d(tangent.Y, -tangent.X, 0)
    return right

def const_normal_srf_from_curve_and_point(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle], 
    point: Union[Point3D, rg.Point3d], 
    height: float = 100000, # 100m
    length: float = 100000, # 100m
) -> rg.Brep:
    point = const_point_obj(point)
    curve = const_curve_obj(curve)
    right_vec = get_normal_vector_on_curve_2d(curve, point)
    srf = const_vertical_srf_from_point_and_axis(point, Vector2D(right_vec.X, right_vec.Y), height=height, length=length)
    return srf


def const_brep_from_all_crvs(crvs, cap=True, tol=0.01):
    crvs = crvs + [crvs[0]]
    breps = []
    for i in range(len(crvs)-1):
        crv1 = crvs[i]
        crv2 = crvs[i+1]
        srf = const_srf_from_2crvs([crv1, crv2])
        breps.append(srf)
    brep = join_breps_or_raise(breps, tol, context="const_brep_from_all_crvs")
    if cap:
        brep = brep.CapPlanarHoles(0.01)
    return brep

def flip_breps(breps: list[rg.Brep]) -> list[rg.Brep]:
    flipped = []
    for b in breps:
        b2 = b.DuplicateBrep()
        b2.Flip()
        flipped.append(b2)
    return flipped


def create_planar_ring_face(
    outer_crv: rg.Curve,
    inner_crv: rg.Curve,
    tol: float,
    context: str,
) -> rg.Brep:
    ring_breps = rg.Brep.CreatePlanarBreps(
        [outer_crv, inner_crv],
        tol,
    )
    if not ring_breps:
        raise ValueError(f"Failed to create ring face: {context}")
    return ring_breps[0]


def const_circular_ring_face(
    center: rg.Point3d,
    tangent: rg.Vector3d,
    outer_radius: float,
    inner_radius: float,
    tol: float,
) -> rg.Brep:
    if inner_radius <= 0:
        raise ValueError(f"inner_radius must be positive: {inner_radius}")
    if outer_radius <= inner_radius:
        raise ValueError(
            f"outer_radius must be larger than inner_radius: "
            f"outer={outer_radius}, inner={inner_radius}"
        )

    plane = rg.Plane(center, tangent)

    outer_crv = rg.Circle(plane, outer_radius).ToNurbsCurve()
    inner_crv = rg.Circle(plane, inner_radius).ToNurbsCurve()

    return create_planar_ring_face(
        outer_crv,
        inner_crv,
        tol,
        context="const_circular_ring_face",
    )


def const_pipe_brep_from_curve(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    outer_radius: float,
    inner_radius: float,
    tol: float = 0.01,
    angle_tol: float = 0.01,
) -> rg.Brep:
    curve = const_curve_obj(curve)

    outer_pipe = rg.Brep.CreatePipe(
        rail=curve,
        radius=outer_radius,
        localBlending=False,
        cap=rg.PipeCapMode(0),
        fitRail=True,
        absoluteTolerance=tol,
        angleToleranceRadians=angle_tol,
    )

    inner_pipe = rg.Brep.CreatePipe(
        rail=curve,
        radius=inner_radius,
        localBlending=False,
        cap=rg.PipeCapMode(0),
        fitRail=True,
        absoluteTolerance=tol,
        angleToleranceRadians=angle_tol,
    )

    if not outer_pipe:
        raise ValueError("Failed to create outer circular pipe surface.")
    if not inner_pipe:
        raise ValueError("Failed to create inner circular pipe surface.")

    t0 = curve.Domain.T0
    t1 = curve.Domain.T1

    p0 = curve.PointAt(t0)
    p1 = curve.PointAt(t1)

    tangent0 = curve.TangentAt(t0)
    tangent1 = curve.TangentAt(t1)

    ring0 = const_circular_ring_face(
        p0,
        tangent0,
        outer_radius,
        inner_radius,
        tol,
    )

    ring1 = const_circular_ring_face(
        p1,
        tangent1,
        outer_radius,
        inner_radius,
        tol,
    )

    breps = []
    breps.extend(outer_pipe)
    breps.extend(flip_breps(inner_pipe))
    breps.extend([ring0, ring1])

    return join_breps_or_raise(
        breps,
        tol=tol,
        context="const_pipe_brep_from_curve",
    )


def const_rectangle_curve_on_plane(
    plane: rg.Plane,
    width: float,
    height: float,
) -> rg.PolylineCurve:
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid rectangle size: width={width}, height={height}")

    half_w = width / 2.0
    half_h = height / 2.0

    pts = [
        plane.PointAt(-half_w, -half_h),
        plane.PointAt( half_w, -half_h),
        plane.PointAt( half_w,  half_h),
        plane.PointAt(-half_w,  half_h),
        plane.PointAt(-half_w, -half_h),
    ]

    return rg.Polyline(pts).ToPolylineCurve()


def const_rectangular_ring_face(
    center: rg.Point3d,
    tangent: rg.Vector3d,
    width: float,
    height: float,
    thickness: float,
    tol: float,
) -> rg.Brep:
    inner_width = width - 2.0 * thickness
    inner_height = height - 2.0 * thickness

    if thickness <= 0:
        raise ValueError(f"thickness must be positive: {thickness}")
    if inner_width <= 0 or inner_height <= 0:
        raise ValueError(
            f"Invalid rectangular pipe size: "
            f"width={width}, height={height}, thickness={thickness}"
        )

    plane = rg.Plane(center, tangent)

    outer_crv = const_rectangle_curve_on_plane(
        plane,
        width,
        height,
    )

    inner_crv = const_rectangle_curve_on_plane(
        plane,
        inner_width,
        inner_height,
    )

    return create_planar_ring_face(
        outer_crv,
        inner_crv,
        tol,
        context="const_rectangular_ring_face",
    )


def const_rectangular_pipe_brep_from_curve(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve],
    width: float,
    height: float,
    thickness: float,
    tol: float = 0.01,
    angle_tol: float = 0.01,
) -> rg.Brep:
    curve = const_curve_obj(curve)

    inner_width = width - 2.0 * thickness
    inner_height = height - 2.0 * thickness

    if thickness <= 0:
        raise ValueError(f"thickness must be positive: {thickness}")
    if inner_width <= 0 or inner_height <= 0:
        raise ValueError(
            f"Invalid rectangular pipe size: "
            f"width={width}, height={height}, thickness={thickness}"
        )

    t0 = curve.Domain.T0
    t1 = curve.Domain.T1

    p0 = curve.PointAt(t0)
    p1 = curve.PointAt(t1)

    tangent0 = curve.TangentAt(t0)
    tangent1 = curve.TangentAt(t1)

    start_plane = rg.Plane(p0, tangent0)

    outer_section = const_rectangle_curve_on_plane(
        start_plane,
        width,
        height,
    )

    inner_section = const_rectangle_curve_on_plane(
        start_plane,
        inner_width,
        inner_height,
    )

    sweep = rg.SweepOneRail()
    sweep.SweepTolerance = tol
    sweep.AngleToleranceRadians = angle_tol
    sweep.ClosedSweep = False

    outer_breps = sweep.PerformSweep(curve, outer_section)
    inner_breps = sweep.PerformSweep(curve, inner_section)

    if not outer_breps:
        raise ValueError("Failed to sweep outer rectangular pipe surface.")
    if not inner_breps:
        raise ValueError("Failed to sweep inner rectangular pipe surface.")

    ring0 = const_rectangular_ring_face(
        p0,
        tangent0,
        width,
        height,
        thickness,
        tol,
    )

    ring1 = const_rectangular_ring_face(
        p1,
        tangent1,
        width,
        height,
        thickness,
        tol,
    )

    breps = []
    breps.extend(outer_breps)
    breps.extend(flip_breps(inner_breps))
    breps.extend([ring0, ring1])

    return join_breps_or_raise(
        breps,
        tol=tol,
        context="const_rectangular_pipe_brep_from_curve",
    )
