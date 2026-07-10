import math
from typing import Union

import Rhino.Geometry as rg

from my_project.config.constants import DISTANCE_TOL
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.geometry.points import interpolate_value_by_distance
from my_project.utils.geometry_gh.const import const_curve_obj, const_point_obj


def point3d_from_rg(point: rg.Point3d, z: Union[float, None] = None) -> Point3D:
    return Point3D(
        x=point.X,
        y=point.Y,
        z=point.Z if z is None else z,
    )


def get_curve_distance(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    point: Union[rg.Point3d, Point3D, Point2D],
) -> float:
    curve = const_curve_obj(curve)
    ok, t = curve.ClosestPoint(const_point_obj(point))
    if not ok:
        raise ValueError("ClosestPoint failed")
    return curve.GetLength(rg.Interval(curve.Domain.Min, t))


def get_polyline_distances(points: list[Point3D]) -> list[float]:
    distances = [0.0]
    for point1, point2 in zip(points, points[1:]):
        distances.append(distances[-1] + const_point_obj(point1).DistanceTo(const_point_obj(point2)))
    return distances


def get_value_at_point_on_polyline(
    points: list[Point3D],
    values: list[float],
    target_point: Point3D,
) -> float:
    distances = get_polyline_distances(points)
    curve = rg.PolylineCurve([const_point_obj(point) for point in points])
    target_distance = get_curve_distance(curve, target_point)
    return interpolate_value_by_distance(
        distances=distances,
        values=values,
        target_distance=target_distance,
    )


def get_curve_polyline_points(curve: rg.Curve) -> list[Point3D]:
    curve = const_curve_obj(curve)
    ok, polyline = curve.TryGetPolyline()
    if ok:
        points = [point3d_from_rg(pt, z=0) for pt in polyline]
    elif isinstance(curve, rg.PolyCurve):
        points = []
        for segment in curve.DuplicateSegments():
            if not points:
                points.append(point3d_from_rg(segment.PointAtStart, z=0))
            points.append(point3d_from_rg(segment.PointAtEnd, z=0))
    else:
        nurbs_curve = curve.ToNurbsCurve()
        if nurbs_curve is None or nurbs_curve.Points.Count == 0:
            raise ValueError(f"Input curve has no usable vertices or control points: {curve}")
        points = [
            point3d_from_rg(nurbs_curve.Points[i].Location, z=0)
            for i in range(nurbs_curve.Points.Count)
        ]
    if len(points) >= 2 and const_point_obj(points[0]).DistanceTo(const_point_obj(points[-1])) < DISTANCE_TOL:
        points = points[:-1]
    return points


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

def get_distance_along_crv(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    points: list[Union[rg.Point3d, Point3D, Point2D]],
) -> list[float]:
    point_distances = []
    for p in points:
        p_obj = const_point_obj(p)
        t = curve.ClosestPoint(p_obj)[1]
        if t == 0:
            distance = 0
        elif t == len(points) - 1:
            distance = curve.GetLength()
        else:
            split_curves = curve.Split(t)
            start_curve = split_curves[0]
            distance = start_curve.GetLength()
        point_distances.append(distance)
    return point_distances

def add_brep_with_boolean_union_or_numbering(
    target_dict: dict,
    key: str,
    brep: rg.Brep,
    tol: float = 0.01,
):
    """
    target_dict[key] が未登録なら brep を登録。
    既に同じ key がある場合は BooleanUnion を試す。

    - 1個にUnionできた場合:
        target_dict[key] = unioned_brep

    - Unionできない / 複数に分かれる場合:
        target_dict[key_1], target_dict[key_2], ... として保存する
    """

    def save_with_numbering(base_key: str, breps: list):
        # 既存の base_key は消す
        if base_key in target_dict:
            del target_dict[base_key]

        # 既存の base_key_1, base_key_2 ... も一度消す
        remove_keys = [
            k for k in target_dict.keys()
            if k.startswith(base_key + "_")
        ]
        for k in remove_keys:
            del target_dict[k]

        # 通し番号で保存
        for i, b in enumerate(breps, start=1):
            target_dict[f"{base_key}_{i}"] = b

    # まだkeyがなければ普通に登録
    if key not in target_dict:
        target_dict[key] = brep
        return

    old = target_dict[key]

    # 念のため、既存値がlistだった場合にも対応
    if isinstance(old, list):
        breps = old + [brep]
    else:
        breps = [old, brep]

    unioned = rg.Brep.CreateBooleanUnion(breps, tol)

    if unioned and len(unioned) == 1:
        # 完全に1個にできた場合
        print(f"BooleanUnion succeeded for {key}, merged into 1 Brep.")
        target_dict[key] = unioned[0]

    elif unioned and len(unioned) > 1:
        # BooleanUnionはできたが、複数ソリッドに分かれた場合
        print(f"BooleanUnion for {key} resulted in {len(unioned)} Breps, saving with numbering.")
        save_with_numbering(key, list(unioned))

    else:
        # BooleanUnion自体が失敗した場合
        print(f"BooleanUnion failed for {key}, saving with numbering.")
        save_with_numbering(key, breps)

def get_point_on_crv_at_distance(
    curve: Union[rg.Curve, rg.Line, rg.PolylineCurve, rg.Circle],
    distance: float,
) -> rg.Point3d:
    crv = const_curve_obj(curve)

    if distance <= 0:
        return crv.PointAtStart

    length = crv.GetLength()
    if distance >= length:
        return crv.PointAtEnd

    ok, t = crv.LengthParameter(distance)
    if not ok:
        raise ValueError(f"Failed to get parameter at distance: {distance}")

    return crv.PointAt(t)
