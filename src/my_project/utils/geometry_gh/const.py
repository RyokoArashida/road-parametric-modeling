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

def const_line_obj(
    start: Union[Point3D, Point2D, rg.Point3d],
    end: Union[Point3D, Point2D, rg.Point3d],
) -> rg.Line:
    return rg.Line(const_point_obj(start), const_point_obj(end))

def const_polycurve_obj(points: list[Union[Point3D, Point2D, rg.Point3d]]) -> rg.PolylineCurve:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 2:
        raise ValueError(f"Need at least 2 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points)
    return rg.PolylineCurve(polyline)

def const_closed_polycurve_obj(
    points: Union[list[Point3D], list[Point2D], list[rg.Point3d]]
) -> rg.PolylineCurve:
    valid_points = [point for point in points if point is not None]
    corner_points = [const_point_obj(point) for point in valid_points]
    if len(corner_points) < 3:
        raise ValueError(f"Need at least 3 valid points, got {len(corner_points)}")
    polyline = rg.Polyline(corner_points + [corner_points[0]])
    curve = rg.PolylineCurve(polyline)
    if not curve.IsClosed:
        raise ValueError(f"Curve is not closed. points={corner_points}")
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
    if isinstance(crv, rg.Curve):
        curve = crv
    elif isinstance(crv, rg.Line):
        curve = rg.LineCurve(crv)
    elif isinstance(crv, rg.PolylineCurve):
        curve = rg.PolylineCurve(crv)
    elif isinstance(crv, rg.Circle):
        curve = crv.ToNurbsCurve()
    else:
        raise ValueError(f"Unsupported object type: {type(crv)}")
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

def const_srf_from_crvs(curves: list[Union[rg.Curve, rg.Line, rg.PolylineCurve]]) -> rg.Brep:
    if len(curves) < 2:
        raise ValueError(f"Need at least 2 curves to loft, got {len(curves)}")
    loft_type = rg.LoftType.Normal
    lofted = rg.Brep.CreateFromLoft(curves, rg.Point3d.Unset, rg.Point3d.Unset, loft_type, False)
    if not lofted or len(lofted) == 0:
        raise ValueError("Loft failed")
    return lofted[0]

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
    srf = const_srf_from_crvs([rg.LineCurve(plus_line), rg.LineCurve(minus_line)])
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
    axis_vector = Vector2D(x=point2.X - point1.X, y=point2.Y - point1.Y)
    srf = const_vertical_srf_from_point_and_axis(mid_pt, axis_vector, height=height, length=length)
    return srf


def const_point_along_curve(curve: rg.Curve, base_point: Union[Point3D, rg.Point3d], offset: float) -> rg.Point3d:
    base_point = const_point_obj(base_point)
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