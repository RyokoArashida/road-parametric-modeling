from typing import Optional

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.I_Box_joint_schemas import (
    BoxPointsInfo,
    IBoxJointFlangeInfo,
    IBoxJointInfo,
    PlatePointsInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_distance_2D,
    get_point_by_xy_offset,
)
from my_project.utils.geometry_gh.const import (
    const_brep_from_all_crvs,
    const_closed_polycurve_obj,
    const_extrude_brep_from_curve,
    const_line_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    join_breps_or_raise,
)
from my_project.utils.geometry_gh.transform import (
    move_obj,
)
from my_project.utils.io import load_from_pickle


def get_flange(
    flange_info: IBoxJointFlangeInfo,
    Plate_I_MG_points_I: PlatePointsInfo,
    Plate_I_MG_points_O: PlatePointsInfo,
    Plate_O_MG_points_I: PlatePointsInfo,
    Plate_O_MG_points_O: PlatePointsInfo,
    Box_I_MG_points_I: BoxPointsInfo,
    Box_I_MG_points_O: BoxPointsInfo,
    Box_O_MG_points_I: BoxPointsInfo,
    Box_O_MG_points_O: BoxPointsInfo,
    top_or_bottom: str,
    web_gap_y: float,
    web_thickness: float,
) -> Optional[rg.Brep]:
    thickness = flange_info.thickness
    if top_or_bottom == "top":
        MG_Plate_O_O = Plate_O_MG_points_O.top_out
        MG_Plate_I_O = Plate_I_MG_points_O.top_out
        MG_Plate_O_I = Plate_O_MG_points_I.top_out
        MG_Plate_I_I = Plate_I_MG_points_I.top_out
        MG_Box_O_O = Box_O_MG_points_O.top_out
        MG_Box_I_O = Box_I_MG_points_O.top_out
        MG_Box_O_I = Box_O_MG_points_I.top_out
        MG_Box_I_I = Box_I_MG_points_I.top_out
        input_MG_Plate_O_web_O = Plate_O_MG_points_O.web_top
        input_MG_Plate_I_web_O = Plate_I_MG_points_O.web_top
        input_MG_Plate_O_web_I = Plate_O_MG_points_I.web_top
        input_MG_Plate_I_web_I = Plate_I_MG_points_I.web_top
        input_MG_Box_O_webO_out = Box_O_MG_points_O.web_top_out
        input_MG_Box_I_webO_out = Box_I_MG_points_O.web_top_out
        input_MG_Box_O_webO_in  = Box_O_MG_points_O.web_top_in
        input_MG_Box_I_webO_in  = Box_I_MG_points_O.web_top_in
        input_MG_Box_O_webI_out = Box_O_MG_points_I.web_top_out
        input_MG_Box_I_webI_out = Box_I_MG_points_I.web_top_out
        input_MG_Box_O_webI_in  = Box_O_MG_points_I.web_top_in
        input_MG_Box_I_webI_in  = Box_I_MG_points_I.web_top_in
        MG_Plate_O_flange_thickness = Plate_O_MG_points_O.top_flange_thickness
        MG_Plate_I_flange_thickness = Plate_I_MG_points_O.top_flange_thickness
        MG_Box_O_flange_thickness = Box_O_MG_points_O.top_flange_thickness
        MG_Box_I_flange_thickness = Box_I_MG_points_O.top_flange_thickness

        MG_Plate_O_web_O = Point3D(input_MG_Plate_O_web_O.x, input_MG_Plate_O_web_O.y, input_MG_Plate_O_web_O.z - (thickness - MG_Plate_O_flange_thickness))
        MG_Plate_I_web_O = Point3D(input_MG_Plate_I_web_O.x, input_MG_Plate_I_web_O.y, input_MG_Plate_I_web_O.z - (thickness - MG_Plate_I_flange_thickness))
        MG_Plate_O_web_I = Point3D(input_MG_Plate_O_web_I.x, input_MG_Plate_O_web_I.y, input_MG_Plate_O_web_I.z - (thickness - MG_Plate_O_flange_thickness))
        MG_Plate_I_web_I = Point3D(input_MG_Plate_I_web_I.x, input_MG_Plate_I_web_I.y, input_MG_Plate_I_web_I.z - (thickness - MG_Plate_I_flange_thickness))
        MG_Box_O_webO_out = Point3D(input_MG_Box_O_webO_out.x, input_MG_Box_O_webO_out.y, input_MG_Box_O_webO_out.z - (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webO_out = Point3D(input_MG_Box_I_webO_out.x, input_MG_Box_I_webO_out.y, input_MG_Box_I_webO_out.z - (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webO_in = Point3D(input_MG_Box_O_webO_in.x, input_MG_Box_O_webO_in.y, input_MG_Box_O_webO_in.z - (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webO_in = Point3D(input_MG_Box_I_webO_in.x, input_MG_Box_I_webO_in.y, input_MG_Box_I_webO_in.z - (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webI_out = Point3D(input_MG_Box_O_webI_out.x, input_MG_Box_O_webI_out.y, input_MG_Box_O_webI_out.z - (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webI_out = Point3D(input_MG_Box_I_webI_out.x, input_MG_Box_I_webI_out.y, input_MG_Box_I_webI_out.z - (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webI_in = Point3D(input_MG_Box_O_webI_in.x, input_MG_Box_O_webI_in.y, input_MG_Box_O_webI_in.z - (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webI_in = Point3D(input_MG_Box_I_webI_in.x, input_MG_Box_I_webI_in.y, input_MG_Box_I_webI_in.z - (thickness - MG_Box_I_flange_thickness))

    elif top_or_bottom == "bottom":
        MG_Plate_O_O = Plate_O_MG_points_O.bottom_out
        MG_Plate_I_O = Plate_I_MG_points_O.bottom_out
        MG_Plate_O_I = Plate_O_MG_points_I.bottom_out
        MG_Plate_I_I = Plate_I_MG_points_I.bottom_out
        MG_Box_O_O = Box_O_MG_points_O.bottom_out
        MG_Box_I_O = Box_I_MG_points_O.bottom_out
        MG_Box_O_I = Box_O_MG_points_I.bottom_out
        MG_Box_I_I = Box_I_MG_points_I.bottom_out
        input_MG_Plate_O_web_O = Plate_O_MG_points_O.web_bottom
        input_MG_Plate_I_web_O = Plate_I_MG_points_O.web_bottom
        input_MG_Plate_O_web_I = Plate_O_MG_points_I.web_bottom
        input_MG_Plate_I_web_I = Plate_I_MG_points_I.web_bottom
        input_MG_Box_O_webO_out = Box_O_MG_points_O.web_bottom_out
        input_MG_Box_I_webO_out = Box_I_MG_points_O.web_bottom_out
        input_MG_Box_O_webO_in  = Box_O_MG_points_O.web_bottom_in
        input_MG_Box_I_webO_in  = Box_I_MG_points_O.web_bottom_in
        input_MG_Box_O_webI_out = Box_O_MG_points_I.web_bottom_out
        input_MG_Box_I_webI_out = Box_I_MG_points_I.web_bottom_out
        input_MG_Box_O_webI_in  = Box_O_MG_points_I.web_bottom_in
        input_MG_Box_I_webI_in  = Box_I_MG_points_I.web_bottom_in        
        MG_Plate_O_flange_thickness = Plate_O_MG_points_O.bottom_flange_thickness
        MG_Plate_I_flange_thickness = Plate_I_MG_points_O.bottom_flange_thickness
        MG_Box_O_flange_thickness = Box_O_MG_points_O.bottom_flange_thickness
        MG_Box_I_flange_thickness = Box_I_MG_points_O.bottom_flange_thickness
        MG_Plate_O_web_O = Point3D(input_MG_Plate_O_web_O.x, input_MG_Plate_O_web_O.y, input_MG_Plate_O_web_O.z + (thickness - MG_Plate_O_flange_thickness))
        MG_Plate_I_web_O = Point3D(input_MG_Plate_I_web_O.x, input_MG_Plate_I_web_O.y, input_MG_Plate_I_web_O.z + (thickness - MG_Plate_I_flange_thickness))
        MG_Plate_O_web_I = Point3D(input_MG_Plate_O_web_I.x, input_MG_Plate_O_web_I.y, input_MG_Plate_O_web_I.z + (thickness - MG_Plate_O_flange_thickness))
        MG_Plate_I_web_I = Point3D(input_MG_Plate_I_web_I.x, input_MG_Plate_I_web_I.y, input_MG_Plate_I_web_I.z + (thickness - MG_Plate_I_flange_thickness))
        MG_Box_O_webO_out = Point3D(input_MG_Box_O_webO_out.x, input_MG_Box_O_webO_out.y, input_MG_Box_O_webO_out.z + (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webO_out = Point3D(input_MG_Box_I_webO_out.x, input_MG_Box_I_webO_out.y, input_MG_Box_I_webO_out.z + (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webO_in = Point3D(input_MG_Box_O_webO_in.x, input_MG_Box_O_webO_in.y, input_MG_Box_O_webO_in.z + (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webO_in = Point3D(input_MG_Box_I_webO_in.x, input_MG_Box_I_webO_in.y, input_MG_Box_I_webO_in.z + (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webI_out = Point3D(input_MG_Box_O_webI_out.x, input_MG_Box_O_webI_out.y, input_MG_Box_O_webI_out.z + (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webI_out = Point3D(input_MG_Box_I_webI_out.x, input_MG_Box_I_webI_out.y, input_MG_Box_I_webI_out.z + (thickness - MG_Box_I_flange_thickness))
        MG_Box_O_webI_in = Point3D(input_MG_Box_O_webI_in.x, input_MG_Box_O_webI_in.y, input_MG_Box_O_webI_in.z + (thickness - MG_Box_O_flange_thickness))
        MG_Box_I_webI_in = Point3D(input_MG_Box_I_webI_in.x, input_MG_Box_I_webI_in.y, input_MG_Box_I_webI_in.z + (thickness - MG_Box_I_flange_thickness))
    else:
        raise ValueError("top_or_bottom should be 'top' or 'bottom'")

    # 全ての点が同一平面上にあればいいのだが、ないので、中心を使ってだましだまし作る
    Plate_midpoint = Point3D(
        (MG_Plate_O_O.x + MG_Plate_I_O.x) / 2,
        (MG_Plate_O_O.y + MG_Plate_I_O.y) / 2,
        (MG_Plate_O_O.z + MG_Plate_I_O.z) / 2,
    )
    Box_midpoint = Point3D(
        (MG_Box_O_O.x + MG_Box_I_O.x) / 2,
        (MG_Box_O_O.y + MG_Box_I_O.y) / 2,
        (MG_Box_O_O.z + MG_Box_I_O.z) / 2,
    )
    Plate_in_midpoint = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=flange_info.Plate_in_y
    )
    Box_in_midpoint = get_point_by_xy_offset(
        point1=Box_midpoint,
        point2=Plate_midpoint,
        offset=flange_info.Box_in_y
    )
    Plate_out_center = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=flange_info.Plate_out_y
    )
    Box_out_midpoint = get_point_by_xy_offset(
        point1=Box_midpoint,
        point2=Plate_midpoint,
        offset=flange_info.Box_out_y
    )
    def get_lr_points(center, reference_center, left_out, right_out, left_offset, right_offset):
        vector = rg.Vector3d(center.x - reference_center.x, center.y - reference_center.y, center.z - reference_center.z)
        left_out_moved = Point3D(left_out.x + vector.X, left_out.y + vector.Y, left_out.z + vector.Z)
        right_out_moved = Point3D(right_out.x + vector.X, right_out.y + vector.Y, right_out.z + vector.Z)
        if left_offset == 0:
            left = left_out_moved
        else:
            left = get_point_by_xy_offset(
                point1 = left_out_moved,
                point2 = center,
                offset = left_offset,
            )
        if right_offset == 0:
            right = right_out_moved
        else:
            right = get_point_by_xy_offset(
                point1 = right_out_moved,
                point2 = center,
                offset = right_offset,
            )
        return left, right
    
    Plate_out_O, Plate_out_I = get_lr_points(Plate_out_center, Plate_midpoint, MG_Plate_O_O, MG_Plate_I_O, 0, 0)
    Box_out_O, Box_out_I = get_lr_points(Box_out_midpoint, Box_midpoint, MG_Box_O_O, MG_Box_I_O, 0, 0)
    Plate_flange_O_width = get_distance_2D(MG_Plate_O_I, MG_Plate_O_O)
    Plate_flange_I_width = get_distance_2D(MG_Plate_I_I, MG_Plate_I_O)
    Box_flange_O_width = get_distance_2D(MG_Box_O_I, MG_Box_O_O)
    Box_flange_I_width = get_distance_2D(MG_Box_I_I, MG_Box_I_O)
    Plate_O_in, Plate_I_in = get_lr_points(Plate_in_midpoint, Plate_midpoint, MG_Plate_O_O, MG_Plate_I_O, Plate_flange_O_width, Plate_flange_I_width)
    Box_O_in, Box_I_in = get_lr_points(Box_in_midpoint, Box_midpoint, MG_Box_O_O, MG_Box_I_O, Box_flange_O_width, Box_flange_I_width)
    
    O_polyline = const_polycurve_obj([MG_Plate_O_O, Plate_out_O, Box_out_O, MG_Box_O_O])
    O_in_polyline = const_polycurve_obj([MG_Plate_O_I, Plate_O_in, Box_O_in, MG_Box_O_I])
    O_mid_polyline = const_polycurve_obj([Plate_O_in, Box_O_in])
    I_mid_polyline = const_polycurve_obj([Plate_I_in, Box_I_in])
    I_in_polyline = const_polycurve_obj([MG_Plate_I_I, Plate_I_in, Box_I_in, MG_Box_I_I])
    I_polyline = const_polycurve_obj([MG_Plate_I_O, Plate_out_I, Box_out_I, MG_Box_I_O])
    srfs = [
        const_srf_from_2crvs([O_polyline, O_in_polyline]),
        const_srf_from_2crvs([O_mid_polyline, I_mid_polyline]),
        const_srf_from_2crvs([I_in_polyline, I_polyline]),
    ]
    srf = join_breps_or_raise(srfs, context="I box joint web")
    
    if top_or_bottom == "top":
        move_vector = rg.Vector3d(0, 0, -thickness)
    elif top_or_bottom == "bottom":
        move_vector = rg.Vector3d(0, 0, thickness)
    moved_srf = move_obj(srf, move_vector)
    polyline = const_closed_polycurve_obj([
        MG_Plate_O_O, MG_Plate_O_I, Plate_O_in, Plate_I_in, MG_Plate_I_I, MG_Plate_I_O, 
        Plate_out_I, Box_out_I, 
        MG_Box_I_O, MG_Box_I_I, Box_I_in, Box_O_in, MG_Box_O_I, MG_Box_O_O,
        Box_out_O, Plate_out_O, 
    ])
    side_srf = const_extrude_brep_from_curve(
        crv=polyline,
        vector=move_vector,
        cap=False,
    )
    srfs = [srf, moved_srf, side_srf]
    flange_brep = join_breps_or_raise(srfs, context="I box joint flange")

    O_out_crv = const_line_obj(MG_Plate_O_web_O, MG_Box_O_webO_out)
    O_in_crv = const_line_obj(MG_Plate_O_web_I, MG_Box_O_webO_in)
    I_out_crv = const_line_obj(MG_Plate_I_web_O, MG_Box_I_webO_out)
    I_in_crv = const_line_obj(MG_Plate_I_web_I, MG_Box_I_webO_in)
    center_distance2D = get_distance_2D(Plate_midpoint, Box_midpoint)
    cross_web_center_y = (center_distance2D - flange_info.Plate_in_y - flange_info.Box_in_y) / 2 + flange_info.Plate_in_y
    cross_web_Plate_out_center = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=cross_web_center_y - web_gap_y - web_thickness
    )
    cross_web_Plate_in_center = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=cross_web_center_y - web_gap_y
    )
    cross_web_Box_in_center = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=cross_web_center_y + web_gap_y
    )
    cross_web_Box_out_center = get_point_by_xy_offset(
        point1=Plate_midpoint,
        point2=Box_midpoint,
        offset=cross_web_center_y + web_gap_y + web_thickness
    )
    cross_web_Plate_O_out, cross_web_Plate_I_out = get_lr_points(cross_web_Plate_out_center, Plate_midpoint, MG_Plate_O_web_I, MG_Plate_I_web_I, 0, 0)
    cross_web_Plate_O_in, cross_web_Plate_I_in = get_lr_points(cross_web_Plate_in_center, Plate_midpoint, MG_Plate_O_web_I, MG_Plate_I_web_I, 0, 0)
    cross_web_Box_O_in_inside_box_O, cross_web_Box_I_in_inside_box_O = get_lr_points(cross_web_Box_in_center, Box_midpoint, MG_Box_O_webO_in, MG_Box_I_webO_in, 0, 0)
    cross_web_Box_O_out_inside_box_O, cross_web_Box_I_out_inside_box_O = get_lr_points(cross_web_Box_out_center, Box_midpoint,MG_Box_O_webO_in, MG_Box_I_webO_in, 0, 0)
    cross_web_Box_O_in_inside_box_I, cross_web_Box_I_in_inside_box_I = get_lr_points(cross_web_Box_in_center, Box_midpoint, MG_Box_O_webI_in, MG_Box_I_webI_in, 0, 0)
    cross_web_Box_O_out_inside_box_I, cross_web_Box_I_out_inside_box_I = get_lr_points(cross_web_Box_out_center, Box_midpoint, MG_Box_O_webI_in, MG_Box_I_webI_in, 0, 0)
    cross_web_Box_O_in_mid, cross_web_Box_I_in_mid = get_lr_points(cross_web_Box_in_center, Box_midpoint, MG_Box_O_webI_out, MG_Box_I_webI_out, 0, 0)
    cross_web_Box_O_out_mid, cross_web_Box_I_out_mid = get_lr_points(cross_web_Box_out_center, Box_midpoint, MG_Box_O_webI_out, MG_Box_I_webI_out, 0, 0)
    
    cross_web_Plate_out_crv =const_line_obj(cross_web_Plate_O_out, cross_web_Plate_I_out)
    cross_web_Plate_in_crv = const_line_obj(cross_web_Plate_O_in, cross_web_Plate_I_in)
    cross_web_Box_O_in_inside_box_crv = const_line_obj(cross_web_Box_O_in_inside_box_O, cross_web_Box_O_in_inside_box_I)
    cross_web_Box_I_in_inside_box_crv = const_line_obj(cross_web_Box_I_in_inside_box_O, cross_web_Box_I_in_inside_box_I)
    cross_web_Box_O_out_inside_box_crv = const_line_obj(cross_web_Box_O_out_inside_box_O, cross_web_Box_O_out_inside_box_I)
    cross_web_Box_I_out_inside_box_crv = const_line_obj(cross_web_Box_I_out_inside_box_O, cross_web_Box_I_out_inside_box_I)
    cross_web_Box_mid_in_crv = const_line_obj(cross_web_Box_O_in_mid, cross_web_Box_I_in_mid)
    cross_web_Box_mid_out_crv = const_line_obj(cross_web_Box_O_out_mid, cross_web_Box_I_out_mid)

    O_Iweb_I, I_Iweb_I = get_lr_points(cross_web_Plate_in_center, Box_midpoint, MG_Box_O_webI_in, MG_Box_I_webI_in, 0, 0)
    O_Iweb_O, I_Iweb_O = get_lr_points(cross_web_Plate_out_center, Box_midpoint, MG_Box_O_webI_out, MG_Box_I_webI_out, 0, 0)
    O_Iweb_I_crv = const_line_obj(MG_Box_O_webI_in, O_Iweb_I)
    I_Iweb_I_crv = const_line_obj(MG_Box_I_webI_in, I_Iweb_I)
    O_Iweb_O_crv = const_line_obj(MG_Box_O_webI_out, O_Iweb_O)
    I_Iweb_O_crv = const_line_obj(MG_Box_I_webI_out, I_Iweb_O)

    web_crv_dist = {
        "left_out": (O_out_crv, O_in_crv),
        "right_out": (I_out_crv, I_in_crv),
        "left_in": (O_Iweb_O_crv, O_Iweb_I_crv),
        "right_in": (I_Iweb_O_crv, I_Iweb_I_crv),
        "cross_web_I": (cross_web_Plate_out_crv, cross_web_Plate_in_crv),
        "cross_web_Box_O": (cross_web_Box_O_out_inside_box_crv, cross_web_Box_O_in_inside_box_crv),
        "cross_web_Box_I": (cross_web_Box_I_out_inside_box_crv, cross_web_Box_I_in_inside_box_crv),
        "cross_web_Box_mid": (cross_web_Box_mid_out_crv, cross_web_Box_mid_in_crv),
    }
    return flange_brep, web_crv_dist


def get_each_joint(
    info : IBoxJointInfo,
) -> dict[str, Optional[rg.Brep]]:
    web_gap_y = info.web_gap_y
    web_thickness = info.web_thickness
    Plate_I_MG_points_I=info.Plate_I_MG_points_I
    Plate_I_MG_points_O=info.Plate_I_MG_points_O
    Plate_O_MG_points_I=info.Plate_O_MG_points_I
    Plate_O_MG_points_O=info.Plate_O_MG_points_O
    Box_I_MG_points_I=info.Box_I_MG_points_I
    Box_I_MG_points_O=info.Box_I_MG_points_O
    Box_O_MG_points_I=info.Box_O_MG_points_I
    Box_O_MG_points_O=info.Box_O_MG_points_O

    top_flange, top_web_crv_dist = get_flange(
        flange_info = info.top_flange_info,
        Plate_I_MG_points_I=Plate_I_MG_points_I,
        Plate_I_MG_points_O=Plate_I_MG_points_O,
        Plate_O_MG_points_I=Plate_O_MG_points_I,
        Plate_O_MG_points_O=Plate_O_MG_points_O,
        Box_I_MG_points_I=Box_I_MG_points_I,
        Box_I_MG_points_O=Box_I_MG_points_O,
        Box_O_MG_points_I=Box_O_MG_points_I,
        Box_O_MG_points_O=Box_O_MG_points_O,
        top_or_bottom = "top",
        web_gap_y = web_gap_y,
        web_thickness = web_thickness,
    )
    bottom_flange, bottom_web_crv_dist = get_flange(
        flange_info = info.bottom_flange_info,
        Plate_I_MG_points_I=Plate_I_MG_points_I,
        Plate_I_MG_points_O=Plate_I_MG_points_O,
        Plate_O_MG_points_I=Plate_O_MG_points_I,
        Plate_O_MG_points_O=Plate_O_MG_points_O,
        Box_I_MG_points_I=Box_I_MG_points_I,
        Box_I_MG_points_O=Box_I_MG_points_O,
        Box_O_MG_points_I=Box_O_MG_points_I,
        Box_O_MG_points_O=Box_O_MG_points_O,
        top_or_bottom = "bottom",
        web_gap_y = web_gap_y,
        web_thickness = web_thickness,
    )
    joint_brep_dict = {
        "top_flange": top_flange,
        "bottom_flange": bottom_flange,
    }
    for key, web_crv_O_I in top_web_crv_dist.items():
        top_O_crv, top_I_crv = web_crv_O_I
        bottom_O_crv, bottom_I_crv = bottom_web_crv_dist[key]
        crvs = [top_O_crv, top_I_crv, bottom_I_crv, bottom_O_crv]
        brep = const_brep_from_all_crvs(crvs)
        joint_brep_dict[key] = brep
    return joint_brep_dict

def main(initial_or_final: str, debug=False):
    DIR = get_output_dir(initial_or_final)

    infos = load_from_pickle(
        file_path=DIR /  f"{Filenames.INPUT}_{Filenames.I_BOX_JOINT}.pickle",
    )

    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}

    if debug:
        all_crvs = []
        for info in infos:
            unique_name = f"{info.Plate_bridge_name}_{info.Box_bridge_name}"
            crvs = get_each_joint(
                info = info,
            )
            all_crvs.extend(crvs)
        return all_crvs

    else:
        for info in infos:
            unique_name = f"{info.Plate_bridge_name}_{info.Box_bridge_name}"
            joint_brep_dict = get_each_joint(
                info = info,
            )
            world_items_dict_for_bake[unique_name] = joint_brep_dict # ここはbake用
        
        def get_keys_and_values_for_bake(world_items_dict):
            flatten_dict_for_bake = flatten_any(world_items_dict)
            items = list(flatten_dict_for_bake.items())
            # valueがNoneのものはbakeできないので除外
            items = [(k,v) for k,v in items if v is not None]
            keys = [k for k, _ in items]
            values = [v for _, v in items]
            return keys, values

        return get_keys_and_values_for_bake(world_items_dict_for_bake)

if __name__ == "__main__":
    (bake_keys, bake_objs) = main("initial")
    # crvs = main("initial", debug=True)
