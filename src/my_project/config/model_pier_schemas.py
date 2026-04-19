from __future__ import annotations

from dataclasses import dataclass

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class Local_PierTopSurfModel:
    DC: Point3D
    UT: Point3D
    DT: Point3D
    UN: Point3D
    DN: Point3D
    UC: Point3D = Point3D(0, 0, 0) # 上り線側中心点

@dataclass(frozen=True)
class Local_ColumnModel:
    UTT: Point3D
    UTN: Point3D
    UNT: Point3D
    UNN: Point3D
    DNN: Point3D
    DNT: Point3D
    DTN: Point3D
    DTT: Point3D

