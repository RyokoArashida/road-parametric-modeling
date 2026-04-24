from __future__ import annotations

from dataclasses import dataclass

from my_project.config.util_schemas import (
    MonoSlope,
    Point3D,
)


@dataclass(frozen=True)
class BarrierCommonInfo:
    slope: MonoSlope
    x: float
    face_x: float
    face_height: float
    haunch_x: float
    haunch_height: float
    base_height: float
    edge_out_height: float
    edge_in_height: float
    edge_watertreatment_height: float
    edge_watertreatment_x: float
    pavement_height: float

@dataclass(frozen=True)
class CenterBarrierNoseInfo:
    length: float
    radius: float
    height: float
    edge_cut_width: float
    start_cross_girder_key: str
    start_offset: float

@dataclass(frozen=True)
class LR_point:
    name: str
    Lpoint: Point3D
    Rpoint: Point3D

@dataclass(frozen=True)
class BarrierInfo:
    bridge_name: str
    num: str
    common_info: BarrierCommonInfo
    slab_edge_points: list[LR_point]

@dataclass(frozen=True)
class CenterBarrierInfo:
    bridge_name: str
    num: str
    barrier_common_info: BarrierCommonInfo
    nose_common_info: CenterBarrierNoseInfo #ノーズまでは再現しないかも…
    LR2_points: list[LR_point]