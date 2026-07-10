from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from my_project.config.util_schemas import MonoSlope, Point3D


@dataclass(frozen=True)
class EdgeStructureInfo:
    structure_type: str
    structure_name: str


@dataclass(frozen=True)
class EdgeSideInfo:
    structure: Optional[EdgeStructureInfo] = None
    U_slope: Optional[float] = None
    D_slope: Optional[float] = None


@dataclass(frozen=True)
class WallTargetInfo:
    target_name: str
    target_num: int
    target_type: str
    target_edge_name: Optional[str]
    target_tier: Optional[int]
    target_position: Optional[str]


@dataclass(frozen=True)
class WallInterferenceInfo:
    wall_main_name: str
    wall_name: str
    berm: Optional[WallTargetInfo] = None
    top: Optional[WallTargetInfo] = None
    bottom: Optional[WallTargetInfo] = None


@dataclass(frozen=True)
class PointsInfo:
    STAs: list[float]
    Upoint: list[Point3D]
    Dpoint: list[Point3D]


@dataclass(frozen=True)
class EmbankmentPaveInfo:
    name: str
    num: int
    points: PointsInfo
    width: float
    thickness: float
    slope: MonoSlope
    start_edge: Optional[EdgeSideInfo] = None
    end_edge: Optional[EdgeSideInfo] = None
    wall_interferences: Optional[list[WallInterferenceInfo]] = None
    start_edge_structure: Optional[EdgeStructureInfo] = None
    end_edge_structure: Optional[EdgeStructureInfo] = None
