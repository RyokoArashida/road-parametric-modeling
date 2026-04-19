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