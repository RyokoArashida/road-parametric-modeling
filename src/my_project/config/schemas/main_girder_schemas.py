from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class GirderBlockInfo:
    CG: str
    CG_offset:float
    top_flange_thickness: float
    bottom_flange_thickness: float
    web_thickness: float

@dataclass(frozen=True)
class WidthChangeInfo:
    CG: str
    y: float
    straight_x: float
    slope_x: float
    change_type: str # start, end, middle

@dataclass(frozen=True)
class HeightChangeInfo:
    start_CG: Optional[str]
    start_offset: Optional[float]
    straight_start_CG: str
    straight_start_offset: float
    straight_end_CG: str
    straight_end_offset: float
    end_CG: Optional[str]
    end_offset: Optional[float]
    height: float

@dataclass(frozen=True)
class TopFlangePointInfo:
    CG: str
    U: Point3D
    C: Point3D
    D: Point3D

@dataclass(frozen=True)
class BottomFlangePointInfo:
    CG: str
    U: Point3D
    C: Point3D
    D: Point3D

@dataclass(frozen=True)
class FlangePointInfo:
    CG: str
    top: TopFlangePointInfo
    bottom: BottomFlangePointInfo

@dataclass(frozen=True)
class MainGirderInfo:
    bridge_name: str
    MG_name: str
    MG_type: str
    basic_height: float
    bottom_flange_width: float
    web_offset: float
    block_infos: List[GirderBlockInfo]
    width_change_infos: List[WidthChangeInfo]
    height_change_infos: List[HeightChangeInfo]
    original_CG_names: List[str]


@dataclass(frozen=True)
class MainGirderCenterPointInfo:
    top_flange_thickness: float
    bottom_flange_thickness: float
    web_thickness: float
    C_top: Optional[Point3D]
    C_bottom: Optional[Point3D]
    L_top: Optional[Point3D] # 箱桁
    L_bottom: Optional[Point3D]
    R_top: Optional[Point3D] # 箱桁
    R_bottom: Optional[Point3D]

