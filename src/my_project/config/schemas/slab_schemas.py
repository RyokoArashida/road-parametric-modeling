from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from my_project.config.schemas.superstructure_schemas import (
    CrossGirderOffsetInfo,
)
from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    MonoSlope,
    Point2D,
    Point3D,
)


@dataclass(frozen=True)
class CommonHeightInfo:
    pavement: float
    edge: float
    girder_above: float

@dataclass(frozen=True)
class CommonWidthInfo:
    girder_flange: float
    edge_offset: float # L/R2から床版端部へのオフセット

@dataclass(frozen=True)
class EmergencyLaneInfo:
    LR: str # L or R
    start_offset: CrossGirderOffsetInfo
    taper_length_N: float
    length: float
    teper_length_T: float
    width: float

@dataclass(frozen=True)
class MainGirderTopPointInfo:
    name: str
    U_edge:Optional[Point3D]
    center:Point3D
    D_edge:Optional[Point3D]

@dataclass(frozen=True)
class BottomSurfaceInfo:
    start_offset: CrossGirderOffsetInfo
    end_offset: CrossGirderOffsetInfo
    slope_width: float
    center_height: float

@dataclass(frozen=True)
class SlabPointInfo:
    name: str
    CL: Optional[Union[Point3D, Point2D]]
    L2: Optional[Union[Point3D, Point2D]]
    R2: Optional[Union[Point3D, Point2D]]
    main_girder_points: Optional[list[MainGirderTopPointInfo]]
    UDframe2D: Optional[Frame2D] # U->Dをx軸、N->Tをy軸とする。原点は上り線側の端っこの梁最上部の中間点。
    UDslope: Optional[MonoSlope] # U->Dの勾配. Uが高い時は正、Dが高い時は負

@dataclass(frozen=True)
class SlabInfo:
    name: str
    num: str
    point_infos: list[SlabPointInfo]
    height: CommonHeightInfo
    width: CommonWidthInfo
    emergency_lane: list[EmergencyLaneInfo]
    bottom_surface: list[BottomSurfaceInfo]
    barrier_type: str

@dataclass(frozen=True)
class DepressedPointInfo:
    pre_girder_name: str
    post_girder_name: str
    start_point: Point3D
    end_point: Point3D

@dataclass(frozen=True)
class SlabCorners:
    name: str
    is_center_depressed: bool
    Utop: Point3D
    Dtop: Point3D
    Ubottom: Point3D
    Dbottom: Point3D
    main_girder_top_points: list[MainGirderTopPointInfo]
    depressed_points: list[DepressedPointInfo]

















@dataclass(frozen=True)
class PointsForVector: # U->Dをx軸、N→Tをy軸とする。原点は上り線側の端っこの梁最上部の中間点。
    point_u: Point2D
    point_d: Point2D

@dataclass(frozen=True)
class SeatInfo:
    y_slope: MonoSlope # 根元から端部へ
    UU_z: float
    UD_z: float
    DU_z: float
    DD_z: float
    U_x: float
    U_center_x: float
    D_center_x: float
    D_x: float
    y: float

@dataclass(frozen=True)
class BackwallInfo:
    UUB_z: float
    DDB_z: float
    UDB_z: float
    DUB_z: float
    UUE_z: float
    DDE_z: float
    UDE_z: float
    DUE_z: float
    y: float

@dataclass(frozen=True)
class WingInfo:
    U_z: float
    D_z: float
    U_x: float
    D_x: float
    Uab_y: float
    Dab_y: float
    Ubl_y: float
    Dbl_y: float
    Uab_height: float
    Dab_height: float
    Ubl_height: float
    Dbl_height: float

@dataclass(frozen=True)
class BarrierInfo:
    U_overhang_Wing: bool # ウィング幅からはみ出しているかどうか
    D_overhang_Wing: bool
    BU_z: float #橋に近い方
    BD_z: float
    CU_z: float #パラペットの境界部
    CD_z: float
    EU_z: float # 土工部に近い方
    ED_z: float
    BU_overhang_width: float # ウィング幅からはみ出している場合のはみ出し幅
    BD_overhang_width: float
    EU_overhang_width: float
    ED_overhang_width: float

@dataclass(frozen=True)
class SlabSeatInfo:
    y: float
    B_ab_height: float
    E_ab_height: float
    height: float
    straight_height: float
    U_x: float
    D_x: float


@dataclass(frozen=True)
class FootingInfo:
    corner_points: Tuple[Point2D, Point2D, Point2D, Point2D]
    reference_point: Point3D
    reference_offset: LocalOffset
    top_z: float
    height: float

@dataclass(frozen=True)
class PileFoundationInfo:
    corner_points: Tuple[Point2D, Point2D, Point2D, Point2D]
    number_of_piles: int
    count_x: int
    count_y: int
    diameter: float
    depths_by_x: List[float]

@dataclass(frozen=True)
class CaissonFoundationInfo:
    reference_point: Point3D
    reference_offset: LocalOffset
    top_z: float
    diameter: float
    depth: float
    centers: List[Point2D]

@dataclass(frozen=True)
class InputAbutInfo:
    points_for_vector: PointsForVector
    ref_point: Point3D
    bridge_type: str # "本線橋" or "ランプ橋"
    abut_type: str # "複橋台" or "単橋台"
    direction: str # "end" or "start" 始点側か終点側か。これでｙ軸の向きを決める
    seat: SeatInfo
    backwall: BackwallInfo
    wing: WingInfo
    barrier: BarrierInfo
    slab_seat: SlabSeatInfo
    footing: Optional[FootingInfo]
    piles: Optional[PileFoundationInfo]
    caisson: Optional[CaissonFoundationInfo]
    notch_position: str # Tokyo or Nagoya

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
class WaterTreatmentNotchInfo:
    outer_x: float
    inner_x: float
    y: float

@dataclass(frozen=True)
class WaterTreatmentWallInfo:
    width: float
    height: float


@dataclass(frozen=True)
class CommonAbutInfo:
    barrier_common_info: BarrierCommonInfo
    notch_info: WaterTreatmentNotchInfo
    wall_info: WaterTreatmentWallInfo


