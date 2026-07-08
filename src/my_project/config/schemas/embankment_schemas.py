from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from my_project.config.util_schemas import MonoSlope, Point3D


@dataclass(frozen=True)
class LocalTopBottomPointInfo:
    top: Point3D
    bottom: Point3D


@dataclass(frozen=True)
class EdgePoints:
    points: list[LocalTopBottomPointInfo]
    wall_points: Optional[list[LocalTopBottomPointInfo]] = None
    wall_positions: Optional[list[int]] = None
    is_wall_only: Optional[list[bool]] = None
    wall_names: Optional[list[Optional[str]]] = None


@dataclass(frozen=True)
class CrossSectionInfo:
    STA: float
    U_points: EdgePoints
    D_points: EdgePoints


@dataclass(frozen=True)
class CorrespondingPointsInfo:
    local: Point3D
    world: Point3D


@dataclass(frozen=True)
class EdgeCrossSectionInfo:
    U_points: EdgePoints
    D_points: EdgePoints
    U_ref_points: list[CorrespondingPointsInfo]
    D_ref_points: list[CorrespondingPointsInfo]


@dataclass(frozen=True)
class EdgeStructureInfo:
    start_section: EdgeCrossSectionInfo
    end_section: EdgeCrossSectionInfo
