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

def transform_local_point_to_world_vertical_plane(
    local_points: list[Union[Point2D, Point3D]],
    world_points: list[Point3D],
    local_target_point: Union[Point2D, Point3D],
    local_z_base_point: Optional[Union[Point2D, Point3D]] = None,
    world_z_base_point: Optional[Point3D] = None,
) -> Point3D:
    if len(local_points) != 2:
        raise ValueError(f"Need 2 local points, got {len(local_points)}")
    if len(world_points) != 2:
        raise ValueError(f"Need 2 world points, got {len(world_points)}")

    local_start, local_end = local_points
    world_start, world_end = world_points
    local_dx = local_end.x - local_start.x
    local_dy = local_end.y - local_start.y
    target_dx = local_target_point.x - local_start.x
    target_dy = local_target_point.y - local_start.y
    if local_dy == 0:
        raise ValueError("local_points have the same y coordinate")
    xy_ratio = target_dy / local_dy
    world_base = interpolate_point_3d(world_start, world_end, xy_ratio)
    world_xy_distance = math.hypot(world_end.x - world_start.x, world_end.y - world_start.y)
    xy_scale = world_xy_distance / abs(local_dy)
    if local_z_base_point is None:
        local_z_base_point = local_start
    if world_z_base_point is None:
        world_z_base_point = world_start
    local_down_delta = local_target_point.x - local_z_base_point.x
    z = world_z_base_point.z - local_down_delta * xy_scale
    return Point3D(
        x=world_base.x,
        y=world_base.y,
        z=z,
    )

def transform_local_point_by_corresponding_points(
    local_points: list[Union[Point2D, Point3D]],
    world_points: list[Point3D],
    local_target_point: Union[Point2D, Point3D],
) -> Point3D:
    if len(local_points) != len(world_points):
        raise ValueError(
            f"local_points and world_points length mismatch: {len(local_points)}, {len(world_points)}"
        )
    if len(local_points) == 2:
        return transform_local_point_to_world_vertical_plane(
            local_points=local_points,
            world_points=world_points,
            local_target_point=local_target_point,
        )
    if len(local_points) != 3:
        raise ValueError(f"Need 2 or 3 corresponding points, got {len(local_points)}")

    def as_3d(point: Union[Point2D, Point3D]) -> Point3D:
        if isinstance(point, Point2D):
            return Point3D(x=point.x, y=point.y, z=0)
        return point

    def sub(point1: Point3D, point0: Point3D) -> Point3D:
        return Point3D(
            x=point1.x - point0.x,
            y=point1.y - point0.y,
            z=point1.z - point0.z,
        )

    def dot(v0: Point3D, v1: Point3D) -> float:
        return v0.x * v1.x + v0.y * v1.y + v0.z * v1.z

    local_0, local_1, local_2 = [as_3d(point) for point in local_points]
    world_0, world_1, world_2 = world_points
    target = as_3d(local_target_point)

    local_v1 = sub(local_1, local_0)
    local_v2 = sub(local_2, local_0)
    local_vt = sub(target, local_0)

    a11 = dot(local_v1, local_v1)
    a12 = dot(local_v1, local_v2)
    a22 = dot(local_v2, local_v2)
    b1 = dot(local_vt, local_v1)
    b2 = dot(local_vt, local_v2)
    det = a11 * a22 - a12 * a12
    if det == 0:
        raise ValueError("local_points are collinear")

    coef1 = (b1 * a22 - b2 * a12) / det
    coef2 = (a11 * b2 - a12 * b1) / det
    world_v1 = sub(world_1, world_0)
    world_v2 = sub(world_2, world_0)
    return Point3D(
        x=world_0.x + world_v1.x * coef1 + world_v2.x * coef2,
        y=world_0.y + world_v1.y * coef1 + world_v2.y * coef2,
        z=world_0.z + world_v1.z * coef1 + world_v2.z * coef2,
    )

def transform_point_to_local_coordinate(
    local_points: list[Union[Point2D, Point3D]],
    world_points: list[Point3D],
    local_target_point: Union[Point2D, Point3D],
    local_z_base_point: Optional[Union[Point2D, Point3D]] = None,
    world_z_base_point: Optional[Point3D] = None,
) -> Point3D:
    return transform_local_point_to_world_vertical_plane(
        local_points=local_points,
        world_points=world_points,
        local_target_point=local_target_point,
        local_z_base_point=local_z_base_point,
        world_z_base_point=world_z_base_point,
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

def get_point_by_xy_offset_with_z_delta(
    point1: Point3D,
    point2: Point3D,
    offset_xy: float, # 正の値のときpoint1から見てpoint2の方向にXYオフセットする
    offset_z: float = 0,
) -> Point3D:
    point_xy = get_point_by_xy_offset(
        point1=Point2D(x=point1.x, y=point1.y),
        point2=Point2D(x=point2.x, y=point2.y),
        offset=offset_xy,
    )
    return Point3D(
        x=point_xy.x,
        y=point_xy.y,
        z=point1.z + offset_z,
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
