from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Vector2D:
    x: float
    y: float

@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float
    
class TravelDirection(Enum):
    UP = "up"       # 上り
    DOWN = "down"   # 下り

class SidePosition(Enum):
    TOKYO = "tokyo"
    NAGOYA = "nagoya"


@dataclass(frozen=True)# 一方向勾配
class MonoSlope:
    value: float

@dataclass(frozen=True)# 中央が高い山形
class CrownSlope:
    value: float

@dataclass(frozen=True)# 中央が低い谷形
class InvertedSlope:
    value: float

@dataclass(frozen=True)
class LocalOffset:
    x: float
    y: float
    z: float

@dataclass(frozen=True)
class Frame2D:
    """
    ローカル2D座標系
    """
    x_axis: Vector2D # U -> D
    y_axis: Vector2D # N -> T

# 点の数に応じて
@dataclass(frozen=True)
class Square_Corners:
    DT: Point3D
    DN: Point3D
    UN: Point3D
    UT: Point3D
    

@dataclass(frozen=True)
class Square_and_center_Corners:
    DC: Point3D
    UT: Point3D
    DT: Point3D
    UN: Point3D
    DN: Point3D
    UC: Point3D = Point3D(0, 0, 0) # 上り線側中心点

@dataclass(frozen=True)
class Octagon_Corners:
    UTT: Point3D
    UTN: Point3D
    UNT: Point3D
    UNN: Point3D
    DNN: Point3D
    DNT: Point3D
    DTN: Point3D
    DTT: Point3D
