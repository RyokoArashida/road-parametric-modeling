import math
from typing import Union

from my_project.config.util_schemas import Frame2D, Point2D, Point3D, Vector2D


def normalize(v: Vector2D) -> Vector2D:
    norm = math.hypot(v.x, v.y)
    if norm == 0:
        raise ValueError("Zero-length vector")
    return Vector2D(v.x / norm, v.y / norm)


def get_frame_2D(point_u: Union[Point2D, Point3D], point_d: Union[Point2D, Point3D], y_direction:str) -> Frame2D:
    if isinstance(point_u, Point3D):
        point_u = Point2D(x=point_u.x, y=point_u.y)
    if isinstance(point_d, Point3D):
        point_d = Point2D(x=point_d.x, y=point_d.y)
    
    # U -> D のベクトルをx軸とする
    raw_x = Vector2D(
        x=point_d.x - point_u.x,
        y=point_d.y - point_u.y
    )
    x_axis = normalize(raw_x)
    if y_direction == "UP":
        y_axis = Vector2D(
            x=-x_axis.y,
            y=x_axis.x,
        ) # x軸に対して反時計回りに90度回転させるとy軸になる →を↑
    elif y_direction == "DOWN":
        y_axis = Vector2D(
            x=x_axis.y,
            y=-x_axis.x,
        ) # x軸に対して時計回りに90度回転させるとy軸になる →を↓
    return Frame2D(
        x_axis=x_axis,
        y_axis=y_axis,
    )


    

