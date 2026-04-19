import math

from my_project.config.util_schemas import Vector2D


def m_coord_to_mm(coord: float) -> float:
    return round(coord * 1000, 1) # 有効数字がmの時に.4桁だったから。

def normalize(v: Vector2D) -> Vector2D:
    norm = math.hypot(v.x, v.y)
    if norm == 0:
        raise ValueError("Zero-length vector")
    return Vector2D(v.x / norm, v.y / norm)

    

