from typing import Any, Optional, Union

from Rhino import Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
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
    if srf is None:
        raise ValueError("Failed to create ruled surface")
    return srf.ToBrep()

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


# そのポイントを通り、与えた軸に沿った、かつ垂直な直線を作る
def const_vertical_line_from_point(
    point: Union[Point3D, rg.Point3d],
    length: float = 100000, # 100m
) -> rg.LineCurve:
    point = const_point_obj(point)
    top = rg.Point3d(point.X, point.Y, point.Z + length / 2)
    bottom = rg.Point3d(point.X, point.Y, point.Z - length / 2)
    line = rg.Line(bottom, top)
    return rg.LineCurve(line)

# そのポイントを通り、与えた軸に沿った、かつ垂直な平面のサーフェスを作る
def const_vertical_srf_from_point_and_axis(
    point: Union[Point3D, rg.Point3d],
    axis_vector: Vector2D,
    height: float = 100000, # 100m
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
    point1: Union[Point3D, rg.Point3d],
    point2: Union[Point3D, rg.Point3d],
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
    brep = rg.Brep.JoinBreps(breps, 0.01)[0]
    if cap:
        brep = brep.CapPlanarHoles(0.01)
    return brep

