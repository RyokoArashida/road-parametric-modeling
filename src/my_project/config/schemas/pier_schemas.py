from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from my_project.config.util_schemas import (
    CrownSlope,
    LocalOffset,
    MonoSlope,
    Point2D,
    Point3D,
)


@dataclass(frozen=True)
class PointsForVector: # U->Dをx軸、N→Tをy軸とする。原点は上り線側の端っこの梁最上部の中間点。
    point_u: Point2D
    point_d: Point2D

@dataclass(frozen=True)
class PierTopSurfInfo:
    """橋座面の情報"""
    reference_point: Point3D
    reference_offset: LocalOffset
    width_y: float
    u2d_slope: MonoSlope
    crown_slope: CrownSlope

@dataclass(frozen=True)
class ColumnInfo:
    """橋脚の柱の情報"""
    outer_x: float #外側のほうが短い
    inner_x: float
    outer_y: float
    inner_y: float # inner_yは橋座面の幅と同じ

@dataclass(frozen=True)
class PierTopHeightProfile:
    """梁の高さの情報"""
    top_U_z: float
    top_D_z: float
    top_z: float
    mid_top_z: float
    bottom_z: float

@dataclass(frozen=True)
class PierTopXProfile:
    pier_top_x_type: Optional[str] # "直線" or "曲線"
    max: Optional[bool]
    x: float

@dataclass(frozen=True)
class PierTopInfo:
    heights: PierTopHeightProfile
    u_side_x: PierTopXProfile
    d_side_x: PierTopXProfile
    between_columns_x: List[PierTopXProfile]

@dataclass(frozen=True)
class FootingInfo:
    corner_points: Tuple[Point2D, Point2D, Point2D, Point2D]
    reference_point: Point3D
    reference_offset: LocalOffset
    height: float

@dataclass(frozen=True)
class PileFoundationInfo:
    corner_points: Tuple[Point2D, Point2D, Point2D, Point2D]
    number_of_piles: int
    count_x: int
    count_y: int
    diameter: float
    depths_by_x: List[float]

@dataclass(frozen=True)
class CaissonFoundationInfo:
    reference_point: Point3D
    reference_offset: LocalOffset
    diameter: float
    depth: float
    centers: List[Point2D]

@dataclass(frozen=True)
class InputPierInfo:
    points_for_vector: PointsForVector
    type: str # "本線橋" or "ランプ橋"
    piertop_surf: PierTopSurfInfo
    column: ColumnInfo
    piertop: PierTopInfo
    footing: Optional[FootingInfo]
    piles: Optional[PileFoundationInfo]
    caisson: Optional[CaissonFoundationInfo]
    notch_position: str # Tokyo or Nagoya

@dataclass(frozen=True)
class WaterTreatmentNotchInfo:
    outer_x: float
    inner_x: float
    y: float

@dataclass(frozen=True)
class WaterTreatmentWallInfo:
    width: float
    height: float

@dataclass(frozen=True)
class MaxPierTopX:
    max_slope_x: float
    max_curve_x: float

@dataclass(frozen=True)
class CommonPierInfo:
    notch_info: WaterTreatmentNotchInfo
    wall_info: WaterTreatmentWallInfo
    max_piertop_x: MaxPierTopX

