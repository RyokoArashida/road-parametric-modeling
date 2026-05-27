from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


@dataclass(frozen=True)
class DrainagePoint:
    y_base_polyline: Optional[str]
    y_base_CG_name: Optional[str]
    y_offset: Optional[Union[float, str]] # adjustmentが入ることがある
    y_adj_ratio: Optional[float] # y_offsetがadjustmentのとき、どれくらい調整するか。0~1で表す
    x_base_polyline: Optional[str]
    x_offset: Optional[Union[float, str]]
    z: Optional[Union[float, str]] # adjustmentが入ることがある

@dataclass(frozen=True)
class PipeInfo:
    name: str
    material: str
    diameter: Optional[float]
    thickness: Optional[float]
    width: Optional[float]
    height: Optional[float]

@dataclass(frozen=True)
class DrainageInfo:
    bridge_name: str
    drainage_name: str
    points: List[DrainagePoint]
    pipes: List[Tuple[int, int, PipeInfo]] #始点終点のインデックス
