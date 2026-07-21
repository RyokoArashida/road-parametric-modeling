from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from my_project.config.util_schemas import Frame2D, MonoSlope, Point3D, Point2D


@dataclass(frozen=True)
class typeInfo:
    type: str # 直線、曲線、クロソイド
    direction: Optional[str] # 曲線のときのみ必要。左カーブか右カーブか
    radius: Optional[float] # arcのときのみ必要
    start_radius: Optional[float] # クロソイドのときのみ必要
    end_radius: Optional[float] # クロソイドのときのみ必要

@dataclass(frozen=True)
class ZInfo:
    STA: float
    z: float
    pre_slope: float # 前の点からの縦断勾配。
    post_slope: float # 次の点への縦断勾配。


@dataclass(frozen=True)
class SlopeInfo:
    STA: float
    slope: MonoSlope


@dataclass(frozen=True)
class EmbankmentPaveInfo:
    slope_infos: list[SlopeInfo]
    width: float


@dataclass(frozen=True)
class RoadSurfaceInfo:
    plan_STAs: list[float] # 各点のSTA。100mm単位＋mm単位
    plan_Coord_infos: list[Point2D]
    z_infos: list[ZInfo]
    type_infos: list[typeInfo]
    
    
