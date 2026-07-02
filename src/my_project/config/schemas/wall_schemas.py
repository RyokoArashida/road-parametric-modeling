from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from my_project.config.util_schemas import Frame2D, MonoSlope, Point3D, Point2D


@dataclass(frozen=True)
class BlockInfo:
    num: int
    front_slope: MonoSlope
    back_slope: MonoSlope
    embed_depth: float
    foundation_front_height: float
    foundation_back_height: float
    foundation_front_offset: float
    block_width: float
    backfill_concrete_width: float
    backfill_stone_top_width: float

@dataclass(frozen=True)
class RefPointInfo:
    top_height: float
    top_num: int
    bottom_num: int

@dataclass(frozen=True)
class WallInfo:
    location: str
    name: str
    wall_type: str #現状ではブロック積みだけ
    block_info: Optional[BlockInfo] # 種類が増えれば適宜増やす
    reference_points: list[RefPointInfo]