from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from my_project.config.util_schemas import MonoSlope, Point3D


@dataclass(frozen=True)
class EdgeStructureInfo:
    structure_type: str #現状ではabutmentのみ
    structure_name: str

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
    thickness: float
    slope: MonoSlope
    start_edge_structure: Optional[EdgeStructureInfo] = None
    end_edge_structure: Optional[EdgeStructureInfo] = None
    
