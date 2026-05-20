from __future__ import annotations

from dataclasses import dataclass

from my_project.config.util_schemas import Point3D


@dataclass(frozen=True)
class IBoxJointFlangeInfo:
    Box_out_y: float
    Plate_out_y: float
    Box_in_y: float
    Plate_in_y: float
    thickness: float

@dataclass(frozen=True)
class PlatePointsInfo:
    top_flange_thickness: float
    bottom_flange_thickness: float
    top_out: Point3D
    top_in: Point3D
    web_top: Point3D
    web_bottom: Point3D
    bottom_in: Point3D
    bottom_out: Point3D
    
@dataclass(frozen=True)
class BoxPointsInfo:
    top_flange_thickness: float
    bottom_flange_thickness: float
    top_out: Point3D
    top_in: Point3D
    web_top_out: Point3D
    web_bottom_out: Point3D
    web_top_in: Point3D
    web_bottom_in: Point3D
    bottom_in: Point3D
    bottom_out: Point3D

@dataclass(frozen=True)
class IBoxJointInfo:
    Plate_bridge_name: str
    Box_bridge_name: str
    Plate_I_MG_points_I: PlatePointsInfo
    Plate_I_MG_points_O: PlatePointsInfo
    Plate_O_MG_points_I: PlatePointsInfo
    Plate_O_MG_points_O: PlatePointsInfo
    Box_I_MG_points_I: BoxPointsInfo
    Box_I_MG_points_O: BoxPointsInfo
    Box_O_MG_points_I: BoxPointsInfo
    Box_O_MG_points_O: BoxPointsInfo
    top_flange_info: IBoxJointFlangeInfo
    bottom_flange_info: IBoxJointFlangeInfo
    web_thickness: float
    web_gap_y: float


