from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class WebInfo:
    thickness: float
    height: Optional[float] = None # 上下フランジ厚も入っている
    edge_height: Optional[float] = None # 上下フランジ厚も入っている

@dataclass(frozen=True)
class FlangeInfo:
    thickness: float
    width: float
    width_plus: float #中心から東京方面のy
    width_minus: float #中心から名古屋方面のy

@dataclass(frozen=True)
class HInfo:
    top_flange: FlangeInfo
    bottom_flange: FlangeInfo
    web: WebInfo

@dataclass(frozen=True)
class LInfo:
    bottom_flange: FlangeInfo
    web: WebInfo

@dataclass(frozen=True)
class EdgeWebInfo:
    thickness: float
    offset: float

@dataclass(frozen=True)
class YokobariInfo:
    web_offset: float
    center_info: HInfo
    outer_extension: bool
    inner_extension: bool
    outer_existence: bool
    inner_existence: bool
    outer_info: Optional[HInfo] = None # 張出
    inner_info: Optional[HInfo] = None # 張出
    outer_edge_info: Optional[EdgeWebInfo] = None #延長のときは端っこにwebもできる
    inner_edge_info: Optional[EdgeWebInfo] = None #延長のときは端っこにwebもできる

@dataclass(frozen=True)
class TaikeikouInfo:
    V_num: int
    center_top_H_offset_z : float # 主桁上面上からH鋼中間まで
    center_top_H_info: HInfo
    center_bottom_H_offset_z : float # 主桁下面上からH鋼中間まで
    center_bottom_H_info: HInfo
    center_L_info: LInfo
    outer_existence: bool
    inner_existence: bool
    outer_info: Optional[HInfo] = None # 張出
    inner_info: Optional[HInfo] = None # 張出

@dataclass(frozen=True)
class YokogetaInfo:
    center_info: HInfo
    outer_existence: bool
    inner_existence: bool
    outer_info: Optional[HInfo] = None # 張出
    inner_info: Optional[HInfo] = None # 張出

@dataclass(frozen=True)
class SlabBottomPoints_IO:
    I: Point3D
    O: Point3D

@dataclass(frozen=True)
class IGirderInfo_IO:
    top_out_I_point: Point3D
    top_out_O_point: Point3D
    top_in_O_point: Point3D
    web_top_O_point: Point3D
    web_bottom_O_point: Point3D
    bottom_in_O_point: Point3D
    bottom_out_O_point: Point3D
    bottom_out_I_point: Point3D
    bottom_in_I_point: Point3D
    web_bottom_I_point: Point3D
    web_top_I_point: Point3D
    top_in_I_point: Point3D

@dataclass(frozen=True)
class BoxGirderInfo_IO:
    top_out_I_point: Point3D
    top_out_O_point: Point3D
    top_in_O_point: Point3D
    Oweb_top_O_point: Point3D
    Oweb_bottom_O_point: Point3D
    bottom_in_O_point: Point3D
    bottom_out_O_point: Point3D
    bottom_out_I_point: Point3D
    bottom_in_I_point: Point3D
    Iweb_bottom_I_point: Point3D
    Iweb_top_I_point: Point3D
    top_in_I_point: Point3D
    Iweb_top_O_point: Point3D
    Oweb_top_I_point: Point3D
    Oweb_bottom_I_point: Point3D
    Iweb_bottom_O_point: Point3D

@dataclass(frozen=True)
class MainGirderPointInfo_IO:
    top_flange_thickness: float
    bottom_flange_thickness: float
    web_thickness: float
    I_points: Optional[IGirderInfo_IO] = None
    Box_points: Optional[BoxGirderInfo_IO] = None

@dataclass(frozen=True)
class CrossGirderInfo:
    bridge_name: str
    CG_name: str
    MGs: list[MainGirderPointInfo_IO] # CLに遠い方から
    slab_bottom_points: SlabBottomPoints_IO
    CG_type: str # 横梁、対傾構、横桁
    yokobari_info: Optional[YokobariInfo] = None
    taikeikou_info: Optional[TaikeikouInfo] = None
    yokogeta_info: Optional[YokogetaInfo] = None
    

