from __future__ import annotations

from dataclasses import dataclass

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class SlabBottomPoints:
    U: Point3D
    D: Point3D