from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class PositionInfo:
    center_x: bool # 中心のxが支承中心と同じｘかどうか
    center_y: bool # 中心のyが支承中心と同じｙかどうか
    near_edge_x: bool #支承中心から近い側の端にxの端が接触しているか
    near_edge_y: bool #支承中心から近い側の端にyの端が接触しているか
    far_edge_y: bool #支承中心から遠い側の端にyの端が接触しているか
    Uedge_x_offset_from_center: Optional[float] # 支承中心からxの左端までの距離
    Nedge_y_offset_from_center: Optional[float] # 支承中心からyの下端までの距離

@dataclass(frozen=True)
class PlateInfo:
    position: PositionInfo
    x: float
    y: float
    height: float

@dataclass(frozen=True)
class ShoeMainInfo:
    main_info: PlateInfo
    top_bottom_plates_height: float
    mid_plates_height: float
    mid_plates_num: int

@dataclass(frozen=True)
class AnkerBoltInfo:
    count_x: int
    count_y: int
    diameter: float
    length: float
    offset_x_list: List[float] # x方向の端からの距離
    offset_y_list: List[float] # y方向の端からの距離


@dataclass(frozen=True)
class CuboidInfo:
    x: float
    y: float
    Uheight: float
    Dheight: float

@dataclass(frozen=True)
class DoubleCuboidInfo:
    x1: float
    y1: float
    x2: float
    y2: float
    Uheight: float
    Cheight: float
    Dheight: float

@dataclass(frozen=True)
class SteppedShapeInfo:
    x: float
    y: float
    Uheight: float
    Dheight: float
    step_y: float
    step_height: float

@dataclass(frozen=True)
class OverhangingInfo:
    x: float
    y: float
    Uheight: float
    Dheight: float
    step_y: float
    step_height: float
    slope_y: float
    slope_height: float

@dataclass(frozen=True)
class FallProtectionInfo:
    position_info: PositionInfo
    fall_protection_type: str
    cuboid: Optional[CuboidInfo] = None
    double_cuboid: Optional[DoubleCuboidInfo] = None
    stepped_shape: Optional[SteppedShapeInfo] = None
    overhanging: Optional[OverhangingInfo] = None

@dataclass(frozen=True)
class ShoeInfo:
    """支承の情報"""
    bridge_name: str
    MG_name: str
    CG_name: str
    substructure_name: str
    center_point: Point3D
    angle: float
    base: Optional[PlateInfo]
    mortar: PlateInfo
    base_plate: PlateInfo
    bottom_plate: PlateInfo
    shoe: ShoeMainInfo
    top_plate: PlateInfo
    anker_bolt: AnkerBoltInfo
    sole_plate_gap_z: Optional[float]
    fall_protection_info: list[FallProtectionInfo]
