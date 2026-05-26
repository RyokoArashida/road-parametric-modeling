from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from my_project.config.util_schemas import (
    Point3D,
)


@dataclass(frozen=True)
class PipeInfo:
    material: str
    diameter: float
    thickness: float
    width: float
    height: float

@dataclass(frozen=True)
class DrainageInfo:
    bridge_name: str
    drainage_name: str
    points: List[Point3D]
    pipes: List[Tuple[List[int], PipeInfo]]
