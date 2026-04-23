from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from my_project.config.util_schemas import Frame2D, MonoSlope, Point3D


@dataclass(frozen=True)
class CoordInfo:
    name: str
    UDframe2D: Frame2D # U->Dをx軸、N->Tをy軸とする。原点は上り線側の端っこの梁最上部の中間点。
    UDslope: MonoSlope # U->Dの勾配. Uが高い時は正、Dが高い時は負
    Points: dict[str, Optional[Point3D]]


@dataclass(frozen=True)
class CrossGirderOffsetInfo:
    name: str
    offset_y: float