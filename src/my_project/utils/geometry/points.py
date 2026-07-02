import math
from typing import Union, Optional

from my_project.config.util_schemas import Frame2D, LocalOffset, Point2D, Point3D
from my_project.config.schemas.superstructure_schemas import CoordInfo


def get_distance_2D(point1: Union[Point2D, Point3D], point2: Union[Point2D, Point3D]) -> float:
    if isinstance(point1, Point2D):
        point1 = Point3D(x=point1.x, y=point1.y, z=0)
    if isinstance(point2, Point2D):
        point2 = Point3D(x=point2.x, y=point2.y, z=0)
    return math.hypot(point2.x - point1.x, point2.y - point1.y)

def get_distance_3D(point1: Point3D, point2: Point3D) -> float:
    return math.sqrt((point2.x - point1.x) ** 2 + (point2.y - point1.y) ** 2 + (point2.z - point1.z) ** 2)

def offset_point_in_frame(
    point: Union[Point3D, Point2D],
    local_offset: LocalOffset,
    frame_2D: Frame2D,
) -> Union[Point3D, Point2D]:
    """pointをframe_2Dのローカル座標系でlocal_offset分だけ移動させる"""
    offset_x = local_offset.x * frame_2D.x_axis.x + local_offset.y * frame_2D.y_axis.x
    offset_y = local_offset.x * frame_2D.x_axis.y + local_offset.y * frame_2D.y_axis.y
    if isinstance(point, Point2D):
        return Point2D(
            x = point.x + offset_x,
            y = point.y + offset_y,
        )
    return Point3D(
        x = point.x + offset_x,
        y = point.y + offset_y,
        z = point.z + local_offset.z,
    )

def interpolate_point_3d(p0: Point3D, p1: Point3D, ratio: float) -> Point3D:
    return Point3D(
        x=p0.x + (p1.x - p0.x) * ratio,
        y=p0.y + (p1.y - p0.y) * ratio,
        z=p0.z + (p1.z - p0.z) * ratio,
    )

def get_point_by_xy_offset(
    point1: Union[Point3D, Point2D],
    point2: Union[Point3D, Point2D],
    offset: float, # 正の値のときpoint1から見てpoint2の方向にオフセットする
) -> Point3D:
    if isinstance(point1, Point2D):
        point1 = Point3D(x=point1.x, y=point1.y, z=0)
    if isinstance(point2, Point2D):
        point2 = Point3D(x=point2.x, y=point2.y, z=0)
    dx = point2.x - point1.x
    dy = point2.y - point1.y
    xy_distance = math.hypot(dx, dy)
    if xy_distance == 0:
        raise ValueError("point1 and point2 have the same XY coordinates")
    t = offset / xy_distance
    return interpolate_point_3d(point1, point2, t)

def get_point_by_xyz_offset(
    point1: Point3D,
    point2: Point3D,
    offset_xyz: float, # 正の値のときpoint1から見てpoint2の方向にオフセットする
) -> Point3D:
    dx = point2.x - point1.x
    dy = point2.y - point1.y
    dz = point2.z - point1.z
    distance = math.sqrt(dx**2 + dy**2 + dz**2)
    if distance == 0:
        raise ValueError("point1 and point2 are the same")
    t = offset_xyz / distance
    return interpolate_point_3d(point1, point2, t)

def get_point_by_xy_z_offset(
    point1: Point3D,
    point2: Point3D,
    offset_xy: float, # 正の値のときpoint1から見てpoint2の方向にオフセットする
    offset_z: float, # 正の値のとき上方向にオフセットする
) -> Point3D:
    point_xy_offset = get_point_by_xy_offset(point1, point2, offset_xy)
    return Point3D(
        x=point_xy_offset.x,
        y=point_xy_offset.y,
        z=point_xy_offset.z + offset_z,
    )

def get_point_by_z_offset_on_line(
    point1: Point3D,
    point2: Point3D,
    offset_z: float, # 正の値のときpoint1から見てpoint2の方向にZ差分だけオフセットする
) -> Point3D:
    dz = point2.z - point1.z
    if dz == 0:
        raise ValueError("point1 and point2 have the same Z coordinate")
    t = offset_z / dz
    return interpolate_point_3d(point1, point2, t)


def get_both_points_by_xy_offset(L_point, R_point, offset_xy):
    return (
        get_point_by_xy_offset(
            point1=L_point,
            point2=R_point,
            offset=offset_xy,
        ),
        get_point_by_xy_offset(
            point1=R_point,
            point2=L_point,
            offset=offset_xy,
        )
    )


def get_point_LR_x_z(L_point, R_point, offset_xy, offset_z): # これはｚが絶対座標
    L_in_line, R_in_line = get_both_points_by_xy_offset(L_point, R_point, offset_xy)
    return (
        Point3D(x=L_in_line.x, y=L_in_line.y, z=L_point.z + offset_z),
        Point3D(x=R_in_line.x, y=R_in_line.y, z=R_point.z + offset_z),
    )

def get_polyline_info_from_coord_info(
    coord_infos: list[CoordInfo],
    target_point_name_list: set[str],
    output_name_by_point_name: Optional[dict[str, str]] = None,
):
    polyline_dict = {}
    output_name_by_point_name = output_name_by_point_name or {}
    for coord_info in coord_infos:
        CG_name = coord_info.name
        points = coord_info.Points
        for point_name, point in points.items():
            if point is None:
                continue
            if point_name in target_point_name_list:
                output_name = output_name_by_point_name.get(point_name, point_name)
                if output_name not in polyline_dict:
                    polyline_dict[output_name] = {
                        "points": [],
                        "point_names": [],
                    }
                polyline_dict[output_name]["points"].append(point)
                polyline_dict[output_name]["point_names"].append(CG_name)
    return polyline_dict


def get_plan_offset_and_z_delta(raw_offset: float, z_slope: Optional[float], z_abs: Optional[float]) -> tuple[float, float]:
    if z_slope is not None:
        slope_factor = math.sqrt(10000 + z_slope**2)
        plan_offset = raw_offset * 100 / slope_factor
        z_delta = -abs(raw_offset) * z_slope / slope_factor # 傾きが正なら落ち、負なら上がる
        return plan_offset, z_delta
    if z_abs is not None:
        return raw_offset, -z_abs
    return raw_offset, 0

def const_point3D_from_point2D(point: Union[Point2D, Point3D]) -> Point3D:
    if isinstance(point, Point3D):
        return point
    return Point3D(x=point.x, y=point.y, z=0)
