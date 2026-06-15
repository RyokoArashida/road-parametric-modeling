from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Sizeinfo:
    width: float
    height: float
    thickness: float

@dataclass(frozen=True)
class RoutePoint:
    x_offset: float
    y_base_CG: str
    y_offset: float
    z_offset: float

@dataclass(frozen=True)
class CrossingInfo:
    side: str # minus or plus
    size_info: Sizeinfo
    length: float
    height_offset: float

@dataclass(frozen=True)
class MainInfo:
    bridge_name: str
    route_name: str
    size_info: Sizeinfo
    base_MG: str
    base_CL: str
    start_point: RoutePoint
    end_point: RoutePoint
    start_crossing: Optional[CrossingInfo]
    end_crossing: Optional[CrossingInfo]
