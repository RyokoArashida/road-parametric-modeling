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
    wall_positions: Optional[list[int]] = None # 段目が入る
    is_wall_only: Optional[list[bool]] = None # 擁壁だけの段かどうか

@dataclass(frozen=True)
class CrossSectionInfo:
    STA: float
    U_points: EdgePoints
    D_points: EdgePoints