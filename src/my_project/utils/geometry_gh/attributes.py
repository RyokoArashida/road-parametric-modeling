import math
from typing import Union

import Rhino.Geometry as rg

from my_project.config.util_schemas import (
    Point2D,
    Point3D,
)
from my_project.utils.geometry_gh.const import const_curve_obj, const_point_obj


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