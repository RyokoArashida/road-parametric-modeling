from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

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
    target_type: Literal["edge", "parallel"]
    target_edge_name: Optional[Literal["start", "end"]]
    target_parallel_name: Optional[Literal["U", "D"]]
    target_tier: Optional[int]
    target_position: Optional[Literal["toe", "shoulder"]]


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
class PavementCrossSlopeInfo:
    STA: float
    slope: MonoSlope


@dataclass(frozen=True)
class EmbankmentPaveInfo:
    name: str
    num: int
    points: Optional[PointsInfo]
    width: Optional[float]
    thickness: float
    slope: MonoSlope
    cross_slope_infos: Optional[list[PavementCrossSlopeInfo]] = None
    start_edge: Optional[EdgeSideInfo] = None
    end_edge: Optional[EdgeSideInfo] = None
    wall_interferences: Optional[list[WallInterferenceInfo]] = None
