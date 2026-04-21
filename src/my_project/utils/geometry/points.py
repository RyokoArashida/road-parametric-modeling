import math
from typing import Union

from my_project.config.util_schemas import Frame2D, LocalOffset, Point2D, Point3D


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



def get_point_by_xy_offset(
    point1: Point3D,
    point2: Point3D,
    offset: float, # 正の値のときpoint1から見てpoint2の方向にオフセットする
) -> Point3D:
    dx = point2.x - point1.x
    dy = point2.y - point1.y
    dz = point2.z - point1.z

    xy_distance = math.hypot(dx, dy)
    if xy_distance == 0:
        raise ValueError("point1 and point2 have the same XY coordinates")
    t = offset / xy_distance
    return Point3D(
        x=point1.x + dx * t,
        y=point1.y + dy * t,
        z=point1.z + dz * t,
    )
