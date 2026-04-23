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

def const_surf_obj_from_points(
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

# そのポイントを通り、与えた軸に沿った、かつ垂直な平面のサーフェスを作る
def const_srf_from_point_and_axis(
    point: Union[Point3D, Point2D, rg.Point3d],
    axis_vector: Vector2D,
    height: float = 100000, # 100m
    length: float = 100000, # 100m
) -> rg.Brep:
    top_plus = rg.Point3d(
        point.x + axis_vector.x * length / 2,
        point.y + axis_vector.y * length / 2,
        point.z + height / 2
    )
    top_minus = rg.Point3d(
        point.x - axis_vector.x * length / 2,
        point.y - axis_vector.y * length / 2,
        point.z + height / 2
    )
    bottom_plus = rg.Point3d(
        point.x + axis_vector.x * length / 2,
        point.y + axis_vector.y * length / 2,
        point.z - height / 2
    )
    bottom_minus = rg.Point3d(
        point.x - axis_vector.x * length / 2,
        point.y - axis_vector.y * length / 2,
        point.z - height / 2
    )
    corners = [top_plus, top_minus, bottom_minus, bottom_plus]
    return const_surf_obj_from_points(corners)