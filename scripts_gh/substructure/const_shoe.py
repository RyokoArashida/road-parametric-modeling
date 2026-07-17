from dataclasses import replace
from typing import Any, Union

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.cross_girder_schemas import (
    MainGirderPointInfo_IO,
)
from my_project.config.schemas.shoe_schemas import (
    AnkerBoltInfo,
    CuboidInfo,
    FallProtectionInfo,
    PlateInfo,
    PositionInfo,
    ShoeInfo,
    SteppedShapeInfo,
)
from my_project.config.util_schemas import (
    LocalOffset,
    Point3D,
    Square_and_center_Corners,
    Square_Corners,
)
from my_project.domain.main_girder import get_MG_polylines
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.vectors import (
    get_frame_2D,
)
from my_project.utils.geometry_gh.const import (
    const_closed_polycurve_obj,
    const_extrude_brep_from_curve,
    const_line_obj,
    const_planer_srf_from_points,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    join_breps_or_raise,
)
from my_project.utils.geometry_gh.intersect import (
    get_closest_point_on_srf_with_point,
    get_intersect_point_on_srf_with_point,
    trim_srf_by_closed_curve,
)
from my_project.utils.geometry_gh.transform import (
    dms_float_to_decimal_degrees,
    move_obj,
    offset_point_in_frame,
    place_obj,
    rotate_point_around_center_xy,
    unplace_obj,
)
from my_project.utils.io import load_from_pickle


def get_MG_bottom_srfs(
    MG_point_dict_for_CG_for_MG: list[MainGirderPointInfo_IO], #あるMGについて
):
    
    MG_polylines = get_MG_polylines(MG_point_dict_for_CG_for_MG)
    bottom_I_polyline = MG_polylines["bottom_out_I_point"]
    bottom_O_polyline = MG_polylines["bottom_out_O_point"]
    bottom_srf = const_srf_from_2crvs([bottom_I_polyline, bottom_O_polyline])
    return bottom_srf

def get_top_srf(
    substructure_top_corners: Union[Square_Corners, Square_and_center_Corners],
) -> rg.Brep:
    if isinstance(substructure_top_corners, Square_and_center_Corners):
        U_corner_points = [substructure_top_corners.UT, substructure_top_corners.UC, substructure_top_corners.UN]
        D_corner_points = [substructure_top_corners.DT, substructure_top_corners.DC, substructure_top_corners.DN]
    else:
        U_corner_points = [substructure_top_corners.UT, substructure_top_corners.UN]
        D_corner_points = [substructure_top_corners.DT, substructure_top_corners.DN]
    U_polyline = const_polycurve_obj(U_corner_points)
    D_polyline = const_polycurve_obj(D_corner_points)
    top_srf = const_srf_from_2crvs([U_polyline, D_polyline])
    return top_srf

def get_near_and_far_edge_and_direction_local(
    center_point: Point3D,
    top_points: Union[Square_Corners, Square_and_center_Corners],
):
    x_max = top_points.DT.x
    y_max = top_points.DT.y
    if center_point.x <= x_max / 2:
        near_x = 0
        far_x = x_max
        direction_x = 1
    else:
        near_x = x_max
        far_x = 0
        direction_x = -1
    if center_point.y <= y_max / 2:
        near_y = 0
        far_y = y_max
        direction_y = 1
    else:
        near_y = y_max
        far_y = 0
        direction_y = -1
    return (near_x, near_y), (far_x, far_y), (direction_x, direction_y)

def get_corners_local(
    x: float,
    y: float,
    position: PositionInfo,
    bottom_center_point: Point3D,
    top_points: Union[Square_Corners, Square_and_center_Corners],
    angle_dms: float = 90,
) -> tuple[Square_Corners, int, int]:
    (near_x, near_y), (far_x, far_y), (direction_x, direction_y) = get_near_and_far_edge_and_direction_local(bottom_center_point, top_points)
    if position.center_x:
        x_min = bottom_center_point.x - x / 2
        x_max = x_min + x
    elif position.near_edge_x:
        if direction_x == 1:
            x_min = near_x
            x_max = near_x + x
        else:
            x_max = near_x
            x_min = near_x - x
    elif position.Uedge_x_offset_from_center is not None:
        x_min = bottom_center_point.x + position.Uedge_x_offset_from_center
        x_max = x_min + x
    else:
        raise ValueError("x方向の位置を特定できません。")
    if position.center_y:
        y_min = bottom_center_point.y - y / 2
        y_max = y_min + y
    elif position.far_edge_y and position.near_edge_y:
        if direction_y == 1:
            y_min = near_y
            y_max = far_y
        else:
            y_max = near_y
            y_min = far_y
    elif position.near_edge_y:
        if direction_y == 1:
            y_min = near_y
            y_max = near_y + y
        else:
            y_max = near_y
            y_min = near_y - y
    elif position.far_edge_y:
        if direction_y == 1:
            y_max = far_y
            y_min = far_y - y
        else:
            y_min = far_y
            y_max = far_y + y
    elif position.Nedge_y_offset_from_center is not None:
        y_min = bottom_center_point.y + position.Nedge_y_offset_from_center
        y_max = y_min + y
    else:
        raise ValueError("y方向の位置を特定できません。")
    corners = Square_Corners(
        DT = Point3D(x_max, y_max, 0),
        DN = Point3D(x_max, y_min, 0),
        UT = Point3D(x_min, y_max, 0),
        UN = Point3D(x_min, y_min, 0),
    )
    if angle_dms == 90:
        return corners, direction_x, direction_y
    angle_deg = dms_float_to_decimal_degrees(angle_dms)
    angle_deg_minus_90 = 90 - angle_deg # 差分だけ回転させるため、90度から引く
    center2D = Point3D(bottom_center_point.x, bottom_center_point.y, 0)
    return Square_Corners(
        DT=rotate_point_around_center_xy(corners.DT, center2D, angle_deg_minus_90),
        DN=rotate_point_around_center_xy(corners.DN, center2D, angle_deg_minus_90),
        UT=rotate_point_around_center_xy(corners.UT, center2D, angle_deg_minus_90),
        UN=rotate_point_around_center_xy(corners.UN, center2D, angle_deg_minus_90),
    ), direction_x, direction_y

def get_bottom_srf_on_unflat_srf(
    x: float,
    y: float,
    position: PositionInfo,
    bottom_center_point: Point3D,
    bottom_srf: rg.Brep,
    bottom_srf_points: Union[Square_Corners, Square_and_center_Corners],
    angle_dms: float,
):
    points2D, direction_x, direction_y = get_corners_local(
        x, 
        y,
        position,
        bottom_center_point, 
        bottom_srf_points, 
        angle_dms
    )
    bottom_points = Square_Corners(
        DT = get_intersect_point_on_srf_with_point(bottom_srf, points2D.DT),
        DN = get_intersect_point_on_srf_with_point(bottom_srf, points2D.DN),
        UT = get_intersect_point_on_srf_with_point(bottom_srf, points2D.UT),
        UN = get_intersect_point_on_srf_with_point(bottom_srf, points2D.UN),
    )
    box_bottom_srfs = trim_srf_by_closed_curve(
        target_srf=bottom_srf,
        cutter_crv=const_closed_polycurve_obj([bottom_points.DT, bottom_points.DN, bottom_points.UN, bottom_points.UT]),
        keep="inside",
    )
    return box_bottom_srfs, bottom_points, direction_x, direction_y

def get_box_on_unflat_srf(
    brep_info: PlateInfo,
    bottom_center_point: Point3D,
    bottom_srf: rg.Brep,
    bottom_srf_points: Union[Square_Corners, Square_and_center_Corners],
    angle_dms: float,
    z_flat: bool,
):
    bottom_srfs, bottom_points, _, _ = get_bottom_srf_on_unflat_srf(
        x = brep_info.x,
        y = brep_info.y,
        position = brep_info.position,
        bottom_center_point = bottom_center_point,
        bottom_srf = bottom_srf,
        bottom_srf_points = bottom_srf_points,
        angle_dms = angle_dms,
    )
    height = brep_info.height
    center_top_z = bottom_center_point.z + height
    if z_flat:
        top_points = Square_Corners(
            DT = Point3D(bottom_points.DT.x, bottom_points.DT.y, center_top_z),
            DN = Point3D(bottom_points.DN.x, bottom_points.DN.y, center_top_z),
            UT = Point3D(bottom_points.UT.x, bottom_points.UT.y, center_top_z),
            UN = Point3D(bottom_points.UN.x, bottom_points.UN.y, center_top_z),
        )
    else:
        top_points = Square_Corners(
            DT = Point3D(bottom_points.DT.x, bottom_points.DT.y, bottom_points.DT.z + height),
            DN = Point3D(bottom_points.DN.x, bottom_points.DN.y, bottom_points.DN.z + height),
            UT = Point3D(bottom_points.UT.x, bottom_points.UT.y, bottom_points.UT.z + height),
            UN = Point3D(bottom_points.UN.x, bottom_points.UN.y, bottom_points.UN.z + height),
        )
    
    top_srf = const_planer_srf_from_points([top_points.DT, top_points.DN, top_points.UN, top_points.UT])
    UT_polyline = const_line_obj(bottom_points.UT, top_points.UT)
    UN_polyline = const_line_obj(bottom_points.UN, top_points.UN)
    DT_polyline = const_line_obj(bottom_points.DT, top_points.DT)
    DN_polyline = const_line_obj(bottom_points.DN, top_points.DN)
    side_srfs = [const_srf_from_2crvs([UT_polyline, DT_polyline]), const_srf_from_2crvs([UN_polyline, DN_polyline])]
    srfs = bottom_srfs + [top_srf] + side_srfs
    return join_breps_or_raise(srfs, context="shoe sole plate").CapPlanarHoles(0.01), center_top_z, top_srf, bottom_points, top_points

def get_box_on_flat_srf(
    brep_info: PlateInfo,
    bottom_center_point: Point3D,
    substructure_top_points: Union[Square_Corners, Square_and_center_Corners],
    bottom_point_z: float,
    angle_dms: float,
):
    points2D, _, _ = get_corners_local(
        brep_info.x,
        brep_info.y,
        brep_info.position, 
        bottom_center_point, 
        substructure_top_points, 
        angle_dms
    )
    height = brep_info.height
    center_top_z = bottom_point_z + height
    bottom_points = Square_Corners(
        DT = Point3D(points2D.DT.x, points2D.DT.y, bottom_point_z),
        DN = Point3D(points2D.DN.x, points2D.DN.y, bottom_point_z),
        UT = Point3D(points2D.UT.x, points2D.UT.y, bottom_point_z),
        UN = Point3D(points2D.UN.x, points2D.UN.y, bottom_point_z),
    )
    bottom_polyline = const_closed_polycurve_obj([bottom_points.DT, bottom_points.DN, bottom_points.UN, bottom_points.UT])
    top_points = Square_Corners(
        DT = Point3D(points2D.DT.x, points2D.DT.y, center_top_z),
        DN = Point3D(points2D.DN.x, points2D.DN.y, center_top_z),
        UT = Point3D(points2D.UT.x, points2D.UT.y, center_top_z),
        UN = Point3D(points2D.UN.x, points2D.UN.y, center_top_z),
    )
    top_polyline = const_closed_polycurve_obj([top_points.DT, top_points.DN, top_points.UN, top_points.UT])
    return const_srf_from_2crvs([bottom_polyline, top_polyline]).CapPlanarHoles(0.01), center_top_z, bottom_points, top_points


def get_shoe_breps(
    shoe_info: ShoeInfo,
    bottom_center_point: Point3D,
    substructure_top_points: Union[Square_Corners, Square_and_center_Corners],
    bottom_point_z: float,
    angle_dms: float,
):
    x = shoe_info.shoe.main_info.x
    y = shoe_info.shoe.main_info.y
    shoe_whole_height = shoe_info.shoe.main_info.height
    top_bottom_plates_height = shoe_info.shoe.top_bottom_plates_height
    mid_plates_height = shoe_info.shoe.mid_plates_height
    mid_plates_num = shoe_info.shoe.mid_plates_num
    rubber_num = mid_plates_num + 1
    rubber_height = (shoe_whole_height - top_bottom_plates_height * 2 - mid_plates_height * mid_plates_num) / rubber_num
    top_bottom_plate_info = PlateInfo(
        x = x,
        y = y,
        height = top_bottom_plates_height,
        position = shoe_info.shoe.main_info.position,
    )
    mid_plate_info = PlateInfo(
        x = x,
        y = y,
        height = mid_plates_height,
        position = shoe_info.shoe.main_info.position,
    )
    rubber_info = PlateInfo(
        x = x,
        y = y,
        height = rubber_height,
        position = shoe_info.shoe.main_info.position,
    )
    brep_dict = {}
    bottom_plate, bottom_plate_center_top_z, _, _ = get_box_on_flat_srf(
        brep_info=top_bottom_plate_info,
        bottom_center_point=bottom_center_point,
        substructure_top_points=substructure_top_points,
        bottom_point_z=bottom_point_z,
        angle_dms=angle_dms,
    )
    brep_dict["bottom_plate"] = bottom_plate
    next_lower_point_z = bottom_plate_center_top_z
    for i in range(mid_plates_num):
        rubber, temp_top_z, _, _ = get_box_on_flat_srf(
            brep_info=rubber_info,
            bottom_center_point=bottom_center_point,
            substructure_top_points=substructure_top_points,
            bottom_point_z=next_lower_point_z,
            angle_dms=angle_dms,
        )
        plate, next_lower_point_z, _, _ = get_box_on_flat_srf(
            brep_info=mid_plate_info,
            bottom_center_point=bottom_center_point,
            substructure_top_points=substructure_top_points,
            bottom_point_z=temp_top_z,
            angle_dms=angle_dms,
        )
        brep_dict[f"rubber_{i + 1}"] = rubber
        brep_dict[f"mid_plate_{i + 1}"] = plate
    rubber, rubber_top_z, _, _ = get_box_on_flat_srf(
        brep_info=rubber_info,
        bottom_center_point=bottom_center_point,
        substructure_top_points=substructure_top_points,
        bottom_point_z=next_lower_point_z,
        angle_dms=angle_dms,
    )
    brep_dict[f"rubber_{rubber_num}"] = rubber
    top_plate, top_plate_center_top_z, _, _ = get_box_on_flat_srf(
        brep_info=top_bottom_plate_info,
        bottom_center_point=bottom_center_point,
        substructure_top_points=substructure_top_points,
        bottom_point_z=rubber_top_z,
        angle_dms=angle_dms,
    )
    brep_dict["top_plate"] = top_plate
    return brep_dict, top_plate_center_top_z

def get_anker_bolt_breps(
    base_plate_info: PlateInfo,
    anker_bolt_info: AnkerBoltInfo,
    base_plate_bottom_points: Square_Corners,
):
    frame2D = get_frame_2D(base_plate_bottom_points.UN, base_plate_bottom_points.DN, "UP")
    def get_center_offsets(offset, full_width):
        edge = (full_width - sum(offset)) / 2
        return [edge] + [edge + sum(offset[:i+1]) for i in range(len(offset))]
    
    x_offsets = get_center_offsets(anker_bolt_info.offset_x_list, base_plate_info.x)
    y_offsets = get_center_offsets(anker_bolt_info.offset_y_list, base_plate_info.y)

    diameter = anker_bolt_info.diameter
    length = anker_bolt_info.length
    x_num = len(x_offsets)
    y_num = len(y_offsets)
    breps = []
    for i in range(x_num):
        for j in range(y_num):
            if i == 0 or i == x_num - 1 or j == 0 or j == y_num - 1: #端しか存在しない
                x_offset = x_offsets[i]
                y_offset = y_offsets[j]
                center_point = offset_point_in_frame(
                    point = base_plate_bottom_points.UN,
                    local_offset=LocalOffset(x=x_offset, y=y_offset, z=0),
                    frame_2D = frame2D,
                )
                circle = rg.Circle(const_point_obj(center_point), diameter/2)
                pile_brep = const_extrude_brep_from_curve(
                    crv = circle,
                    vector = rg.Vector3d(0, 0, -length),
                    cap=True,
                )
                breps.append(pile_brep)
    return breps

def get_sole_plate_brep(
    top_plate_top_points: Square_Corners,
    MG_bottom_srf: rg.Brep,
):
    bottom_points = top_plate_top_points
    top_points = Square_Corners( # ぎりぎり交差しないことがあるので最近傍の点を取る
        DT = get_closest_point_on_srf_with_point(MG_bottom_srf, bottom_points.DT),
        DN = get_closest_point_on_srf_with_point(MG_bottom_srf, bottom_points.DN),
        UT = get_closest_point_on_srf_with_point(MG_bottom_srf, bottom_points.UT),
        UN = get_closest_point_on_srf_with_point(MG_bottom_srf, bottom_points.UN),
    )
    bottom_polyline = const_closed_polycurve_obj([bottom_points.DT, bottom_points.DN, bottom_points.UN, bottom_points.UT])
    top_polyline = const_closed_polycurve_obj([top_points.DT, top_points.DN, top_points.UN, top_points.UT])
    return const_srf_from_2crvs([bottom_polyline, top_polyline]).CapPlanarHoles(0.01)

def get_indiv_shoe_brep(
    shoe_info: ShoeInfo,
    center_point_local: Point3D,
    top_srf_local: rg.Brep,
    top_points_local: Union[Square_Corners, Square_and_center_Corners],
    angle_dms: float,
) :
    local_breps = {}
    if shoe_info.base is not None:
        base_brep_local, base_center_top_z, base_top_srf_local, _, base_top_points_local = get_box_on_unflat_srf(
            brep_info=shoe_info.base,
            bottom_center_point=center_point_local,
            bottom_srf=top_srf_local,
            bottom_srf_points=top_points_local,
            angle_dms=90, # 台座は基本的に回転しない。
            z_flat=False # 台座は下部工と並行
        )
        local_breps["base"] = base_brep_local
        mortar_center_point = Point3D(center_point_local.x, center_point_local.y, base_center_top_z)
        mortar_brep_local, mortar_center_top_z, _, _, _ = get_box_on_unflat_srf(
            brep_info=shoe_info.mortar,
            bottom_center_point=mortar_center_point,
            bottom_srf=base_top_srf_local,
            bottom_srf_points=base_top_points_local,
            angle_dms=angle_dms, 
            z_flat=True, # モルタルで調整
        ) 
        local_breps["mortar"] = mortar_brep_local
    else:
        base_top_srf_local, base_top_points_local = top_srf_local, top_points_local
        mortar_brep_local, mortar_center_top_z, _, _, _ = get_box_on_unflat_srf(
            brep_info=shoe_info.mortar,
            bottom_center_point=center_point_local,
            bottom_srf=base_top_srf_local,
            bottom_srf_points=base_top_points_local,
            angle_dms=angle_dms,
            z_flat=True, # モルタルで調整
        )
        local_breps["mortar"] = mortar_brep_local
    
    base_plate_brep_local, base_plate_center_top_z, base_plate_bottom_points, _= get_box_on_flat_srf(
        brep_info=shoe_info.base_plate,
        bottom_center_point=center_point_local,
        substructure_top_points=top_points_local,
        bottom_point_z=mortar_center_top_z,
        angle_dms=angle_dms,
    )
    local_breps["base_plate"] = base_plate_brep_local

    bottom_plate_brep_local, bottom_plate_center_top_z, _, _ = get_box_on_flat_srf(
        brep_info=shoe_info.bottom_plate,
        bottom_center_point=center_point_local,
        substructure_top_points=top_points_local,
        bottom_point_z=base_plate_center_top_z,
        angle_dms=angle_dms,
    )
    local_breps["bottom_plate"] = bottom_plate_brep_local

    shoe_breps_local, shoe_center_top_z = get_shoe_breps(
        shoe_info=shoe_info,
        bottom_center_point=center_point_local,
        substructure_top_points=top_points_local,
        bottom_point_z=bottom_plate_center_top_z,
        angle_dms=angle_dms,
    )
    local_breps["shoe"] = shoe_breps_local

    top_plate_brep_local, _, _, top_plate_top_points = get_box_on_flat_srf(
        brep_info=shoe_info.top_plate,
        bottom_center_point=center_point_local,
        substructure_top_points=top_points_local,
        bottom_point_z=shoe_center_top_z,
        angle_dms=angle_dms,
    )
    local_breps["top_plate"] = top_plate_brep_local

    anker_bolt_breps_local = get_anker_bolt_breps(
        base_plate_info=shoe_info.base_plate,
        anker_bolt_info=shoe_info.anker_bolt,
        base_plate_bottom_points=base_plate_bottom_points,
    )
    for i, brep in enumerate(anker_bolt_breps_local):
        local_breps[f"anker_bolt_{i + 1}"] = brep

    return local_breps, top_plate_top_points

def get_cuboid(
    brep_info: CuboidInfo,
    bottom_srfs: list[rg.Brep],
    bottom_points: Square_Corners,
) -> rg.Brep:
    Uheight = brep_info.Uheight
    Dheight = brep_info.Dheight
    top_points = Square_Corners(
        DT = Point3D(bottom_points.DT.x, bottom_points.DT.y, bottom_points.DT.z + Dheight),
        DN = Point3D(bottom_points.DN.x, bottom_points.DN.y, bottom_points.DN.z + Dheight),
        UT = Point3D(bottom_points.UT.x, bottom_points.UT.y, bottom_points.UT.z + Uheight),
        UN = Point3D(bottom_points.UN.x, bottom_points.UN.y, bottom_points.UN.z + Uheight),
    )
    top_srf = const_planer_srf_from_points([top_points.DT, top_points.DN, top_points.UN, top_points.UT])
    UT_polyline = const_line_obj(bottom_points.UT, top_points.UT)
    UN_polyline = const_line_obj(bottom_points.UN, top_points.UN)
    DT_polyline = const_line_obj(bottom_points.DT, top_points.DT)
    DN_polyline = const_line_obj(bottom_points.DN, top_points.DN)
    side_srfs = [const_srf_from_2crvs([UT_polyline, DT_polyline]), const_srf_from_2crvs([UN_polyline, DN_polyline])]
    srfs = bottom_srfs + [top_srf] + side_srfs
    return join_breps_or_raise(srfs, context="shoe anker bolt").CapPlanarHoles(0.01)

def get_double_cuboid(
    brep_info: CuboidInfo,
    bottom_srfs: list[rg.Brep],
    bottom_points1: Square_Corners,
    bottom_points2: Square_Corners,
) -> rg.Brep:
    bottom_UT = bottom_points1.UT
    bottom_UN = bottom_points1.UN
    bottom_CT1 = bottom_points1.DT
    bottom_CN1 = bottom_points1.DN
    bottom_CT2 = bottom_points2.UT
    bottom_CN2 = bottom_points2.UN
    bottom_DT = bottom_points2.DT
    bottom_DN = bottom_points2.DN
    [top_UT, top_UN] = [Point3D(pt.x, pt.y, pt.z + brep_info.Uheight) for pt in [bottom_UT, bottom_UN]]
    [top_CT1, top_CN1, top_CT2, top_CN2] = [Point3D(pt.x, pt.y, pt.z + brep_info.Cheight) for pt in [bottom_CT1, bottom_CN1, bottom_CT2, bottom_CN2]]
    [top_DT, top_DN] = [Point3D(pt.x, pt.y, pt.z + brep_info.Dheight) for pt in [bottom_DT, bottom_DN]]
    bottom_T_polyline = const_polycurve_obj([bottom_UT, bottom_CT1, bottom_CT2, bottom_DT])
    bottom_N_polyline = const_polycurve_obj([bottom_UN, bottom_CN1, bottom_CN2, bottom_DN])
    top_T_polyline = const_polycurve_obj([top_UT, top_CT1, top_CT2, top_DT])
    top_N_polyline = const_polycurve_obj([top_UN, top_CN1, top_CN2, top_DN])
    T_srf = const_srf_from_2crvs([bottom_T_polyline, top_T_polyline])
    N_srf = const_srf_from_2crvs([bottom_N_polyline, top_N_polyline])
    top_srf1 = const_planer_srf_from_points([top_UT, top_CT1, top_CN1, top_UN])
    top_srf2 = const_planer_srf_from_points([top_DT, top_CT2, top_CN2, top_DN])
    srfs = bottom_srfs + [T_srf, N_srf, top_srf1, top_srf2]
    return join_breps_or_raise(srfs, context="fall protection base plate").CapPlanarHoles(0.01)


def get_stepped_shape(
    brep_info: SteppedShapeInfo,
    bottom_srfs: list[rg.Brep],
    bottom_points: Square_Corners,
    y_direction: int,
) -> rg.Brep:
    Uheight = brep_info.Uheight
    Dheight = brep_info.Dheight
    step_height = brep_info.step_height
    step_y = brep_info.step_y
    if y_direction == 1: # ↑
        bottom_UI, bottom_DI = bottom_points.UT, bottom_points.DT
        bottom_UO, bottom_DO = bottom_points.UN, bottom_points.DN
    else: # ↓
        bottom_UI, bottom_DI = bottom_points.UN, bottom_points.DN
        bottom_UO, bottom_DO = bottom_points.UT, bottom_points.DT
    bottom_O_polyline = const_line_obj(bottom_UO, bottom_DO)
    bottom_I_polyline = const_line_obj(bottom_UI, bottom_DI)
    top_UO = move_obj(bottom_UO, rg.Vector3d(0, 0, Uheight))
    top_DO = move_obj(bottom_DO, rg.Vector3d(0, 0, Dheight))
    top_O_polyline = const_line_obj(top_UO, top_DO)
    top_UI = move_obj(bottom_UI, rg.Vector3d(0, 0, Uheight - step_height))
    top_DI = move_obj(bottom_DI, rg.Vector3d(0, 0, Dheight - step_height))
    top_I_polyline = const_line_obj(top_UI, top_DI)
    top_step_polyline = move_obj(top_O_polyline, rg.Vector3d(0, y_direction * step_y, 0))
    bottom_step_polyline = move_obj(top_step_polyline, rg.Vector3d(0, 0, -step_height))
    polylines = [bottom_I_polyline, top_I_polyline, bottom_step_polyline, top_step_polyline, top_O_polyline, bottom_O_polyline]
    srfs = bottom_srfs
    for i in range(len(polylines) - 1):
        srfs.append(const_srf_from_2crvs([polylines[i], polylines[i + 1]]))
    return join_breps_or_raise(srfs, context="fall protection wall").CapPlanarHoles(0.01)
    
def get_overhanging_shape(
    brep_info: SteppedShapeInfo,
    bottom_srfs: list[rg.Brep],
    bottom_points: Square_Corners,
    y_direction: int,
) -> rg.Brep:
    Uheight = brep_info.Uheight
    Dheight = brep_info.Dheight
    step_height = brep_info.step_height
    step_y = brep_info.step_y
    slope_height = brep_info.slope_height
    slope_y = brep_info.slope_y
    if y_direction == 1: # ↑
        bottom_UI, bottom_DI = bottom_points.UT, bottom_points.DT
        bottom_UO, bottom_DO = bottom_points.UN, bottom_points.DN
    else: # ↓
        bottom_UI, bottom_DI = bottom_points.UN, bottom_points.DN
        bottom_UO, bottom_DO = bottom_points.UT, bottom_points.DT
    bottom_O_polyline = const_line_obj(bottom_UO, bottom_DO)
    bottom_I_polyline = const_line_obj(bottom_UI, bottom_DI)
    slope_U = move_obj(bottom_UO, rg.Vector3d(0, -y_direction * slope_y, slope_height)) #外側に広がる
    slope_D = move_obj(bottom_DO, rg.Vector3d(0, -y_direction * slope_y, slope_height))
    slope_polyline = const_line_obj(slope_U, slope_D)
    top_UO = move_obj(slope_U, rg.Vector3d(0, 0, Uheight - slope_height))
    top_DO = move_obj(slope_D, rg.Vector3d(0, 0, Dheight - slope_height))
    top_O_polyline = const_line_obj(top_UO, top_DO)
    top_UI = move_obj(bottom_UI, rg.Vector3d(0, 0, Uheight - step_height))
    top_DI = move_obj(bottom_DI, rg.Vector3d(0, 0, Dheight - step_height))
    top_I_polyline = const_line_obj(top_UI, top_DI)
    top_step_polyline = move_obj(top_O_polyline, rg.Vector3d(0, y_direction * step_y, 0))
    bottom_step_polyline = move_obj(top_step_polyline, rg.Vector3d(0, 0, -step_height))
    polylines = [bottom_I_polyline, top_I_polyline, bottom_step_polyline, top_step_polyline, top_O_polyline, slope_polyline, bottom_O_polyline]
    srfs = bottom_srfs
    for i in range(len(polylines) - 1):
        srfs.append(const_srf_from_2crvs([polylines[i], polylines[i + 1]]))
    return join_breps_or_raise(srfs, context="fall protection bracket").CapPlanarHoles(0.01)
    

def get_indiv_fall_protecition_brep(
    fall_protection_info: FallProtectionInfo,
    center_point_local: Point3D,
    top_srf_local: rg.Brep,
    top_points_local: Union[Square_Corners, Square_and_center_Corners],
):
    position_info = fall_protection_info.position_info
    if fall_protection_info.double_cuboid is not None:
        fall_protection_type = "double_cuboid"
        brep_info = fall_protection_info.double_cuboid
        position_info2 = replace(
            position_info,
            Uedge_x_offset_from_center=position_info.Uedge_x_offset_from_center + brep_info.x1,
        )
        bottom_srfs1, bottom_points1, _, _ = get_bottom_srf_on_unflat_srf(
            x = brep_info.x1,
            y = brep_info.y1,
            position = position_info,
            bottom_center_point = center_point_local,
            bottom_srf = top_srf_local,
            bottom_srf_points = top_points_local,
            angle_dms = 90, # 落下防止装置は基本的に回転させない。
        )
        bottom_srfs2, bottom_points2, _, _ = get_bottom_srf_on_unflat_srf(
            x = brep_info.x2,
            y = brep_info.y2,
            position = position_info2,
            bottom_center_point = center_point_local,
            bottom_srf = top_srf_local,
            bottom_srf_points = top_points_local,
            angle_dms = 90, # 落下防止装置は基本的に回転させない。
        )
        return get_double_cuboid(
            brep_info=brep_info,
            bottom_srfs = bottom_srfs1 + bottom_srfs2,
            bottom_points1=bottom_points1,
            bottom_points2=bottom_points2,
        )

    if fall_protection_info.cuboid is not None:
        fall_protection_type = "cuboid"
        brep_info = fall_protection_info.cuboid
    elif fall_protection_info.stepped_shape is not None:
        fall_protection_type = "stepped_shape"
        brep_info = fall_protection_info.stepped_shape
    elif fall_protection_info.overhanging is not None:
        fall_protection_type = "overhanging"
        brep_info = fall_protection_info.overhanging
    else:
        raise ValueError("不正な落下防止装置の種類です。")
    bottom_srfs, bottom_points, _, y_direction = get_bottom_srf_on_unflat_srf(
        x = brep_info.x,
        y = brep_info.y,
        position = position_info,
        bottom_center_point = center_point_local,
        bottom_srf = top_srf_local,
        bottom_srf_points = top_points_local,
        angle_dms = 90, # 落下防止装置は基本的に回転させない。
    )
    if fall_protection_type == "cuboid":
        return get_cuboid(
            brep_info=brep_info,
            bottom_srfs=bottom_srfs,
            bottom_points=bottom_points,
        )
    elif fall_protection_type == "stepped_shape":
        return get_stepped_shape(
            brep_info=brep_info,
            bottom_srfs=bottom_srfs,
            bottom_points=bottom_points,
            y_direction=y_direction,
        )
    elif fall_protection_type == "overhanging":
        return get_overhanging_shape(
            brep_info=brep_info,
            bottom_srfs=bottom_srfs,
            bottom_points=bottom_points,
            y_direction=y_direction,
        )
    
def get_indiv_shoe_and_fall_protection_brep(
    shoe_info: ShoeInfo,
    substructure_top_info: dict[str, dict[str, Any]],
    MG_bottom_srf: rg.Brep,
):
    bridge_name = shoe_info.bridge_name
    MG_name = shoe_info.MG_name
    CG_name = shoe_info.CG_name
    shoe_name = f"{bridge_name}_{MG_name}_{CG_name}"

    substructure_name = shoe_info.substructure_name
    input_center_point_world = shoe_info.center_point
    angle_dms = shoe_info.angle

    def to_local(obj):
        return unplace_obj(
            obj=obj,
            local_origin=Point3D(0, 0, 0),
            world_origin=top_points.UN,
            frame_2D=frame_2D,
        )

    def to_world(obj):
        return place_obj(
            obj=obj,
            local_origin=Point3D(0, 0, 0),
            world_origin=top_points.UN,
            frame_2D=frame_2D,
        )

    if substructure_name not in substructure_top_info:
        return shoe_name, None, None
    top_point_info = substructure_top_info[substructure_name]
    frame_2D = top_point_info["frame_2D"]
    top_srf = top_point_info["top_srf"]
    top_points = top_point_info["top_corners"]

    top_srf_local = to_local(top_srf)
    if isinstance(top_points, Square_and_center_Corners):
        top_points_local = Square_and_center_Corners(
            DC = to_local(top_points.DC),
            UT = to_local(top_points.UT),
            DT = to_local(top_points.DT),
            UN = to_local(top_points.UN),
            UC = to_local(top_points.UC),
            DN = to_local(top_points.DN),
        )
    else:
        top_points_local = Square_Corners(
            DT = to_local(top_points.DT),
            DN = to_local(top_points.DN),
            UT = to_local(top_points.UT),
            UN = to_local(top_points.UN),
        )
    input_center_point_local = to_local(input_center_point_world)

    #ここからはローカル座標系
    center_point_local = get_intersect_point_on_srf_with_point(
        top_srf_local,
        input_center_point_local,
    )

    shoe_dict_local, top_plate_top_points_local = get_indiv_shoe_brep(
        shoe_info=shoe_info,
        center_point_local=center_point_local,
        top_srf_local=top_srf_local,
        top_points_local=top_points_local,
        angle_dms=angle_dms,
    )
    shoe_breps_world = {}
    for key, value in shoe_dict_local.items():
        if isinstance(value, dict): # shoeの中身
            shoe_breps_world[key] = {}
            for key2, value2 in value.items():
                shoe_breps_world[key][key2] = to_world(value2)
        else:
            shoe_breps_world[key] = to_world(value)

    #最後のソールプレートだけはworld座標系になる。
    top_plate_top_points_world = Square_Corners(
        DT = to_world(top_plate_top_points_local.DT),
        DN = to_world(top_plate_top_points_local.DN),
        UT = to_world(top_plate_top_points_local.UT),
        UN = to_world(top_plate_top_points_local.UN),
    )
    sole_plate_brep_world = get_sole_plate_brep(
        top_plate_top_points=top_plate_top_points_world,
        MG_bottom_srf=MG_bottom_srf,
    )
    shoe_breps_world["sole_plate"] = sole_plate_brep_world

    fall_protection_info = shoe_info.fall_protection_info
    if len(fall_protection_info) == 0:
        return shoe_name, shoe_breps_world, None
    fall_protection_breps_world = {}
    for i, fall_protection in enumerate(fall_protection_info):
        fall_protection_brep_world = get_indiv_fall_protecition_brep(
            fall_protection_info=fall_protection,
            center_point_local=center_point_local,
            top_srf_local=top_srf_local,
            top_points_local=top_points_local,
        )
        fall_protection_breps_world[i + 1] = to_world(fall_protection_brep_world)
    return shoe_name, shoe_breps_world, fall_protection_breps_world

def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)

    abut_top_point_dict = load_from_pickle(DIR /  f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.TOP}_{Filenames.POINTS}.pickle")
    pier_top_point_dict = load_from_pickle(DIR /  f"{Filenames.WORLD}_{Filenames.PIER}_{Filenames.TOP}_{Filenames.POINTS}.pickle")
    MG_point_IO_dict = load_from_pickle(DIR / f"{Filenames.WORLD}_{Filenames.MG}_{Filenames.POINTS}_IO.pickle")

    all_shoe_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.SHOE}.pickle")

    substructure_top_point_dict = {**abut_top_point_dict, **pier_top_point_dict}
    for _, value in substructure_top_point_dict.items():
        value["top_srf"] = get_top_srf(value["top_corners"])

    MG_bottom_srf_dict = {}
    for bridge_name, MG_point_dict in MG_point_IO_dict.items():
        MG_bottom_srf_dict[bridge_name] = {}
        for MG_name, MG_point_infos in MG_point_dict.items():
            MG_bottom_srf = get_MG_bottom_srfs(MG_point_infos)
            MG_bottom_srf_dict[bridge_name][MG_name] = MG_bottom_srf
            
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    bridge_seat_points_for_bake = {}

    if debug:
        all_points = []
        all_breps = []
        for shoe_info in all_shoe_infos:
            bridge_name = shoe_info.bridge_name
            MG_name = shoe_info.MG_name
            MG_bottom_srf = MG_bottom_srf_dict[bridge_name][MG_name]
            points, breps = get_indiv_shoe_brep(shoe_info, substructure_top_point_dict, MG_bottom_srf)
 
            all_points.extend(points)
            all_breps.extend(breps)
        return all_points, all_breps
            
    else:
        for substructure_name, top_point_info in substructure_top_point_dict.items():
            bridge_seat_points_for_bake[substructure_name] = top_point_info["top_corners"]

        for shoe_info in all_shoe_infos:
            bridge_name = shoe_info.bridge_name
            MG_name = shoe_info.MG_name
            MG_bottom_srf = MG_bottom_srf_dict[bridge_name][MG_name]
            shoe_name, shoe_brep_dict, fall_protection_brep_dict = get_indiv_shoe_and_fall_protection_brep(shoe_info, substructure_top_point_dict, MG_bottom_srf)
            world_items_dict_for_bake[shoe_name] = shoe_brep_dict # ここはbake用
            world_items_dict_for_bake_2[shoe_name] = fall_protection_brep_dict # ここはbake用

        
        return (
            get_keys_and_values_for_bake(world_items_dict_for_bake),
            get_keys_and_values_for_bake(world_items_dict_for_bake_2),
            get_keys_and_values_for_bake(bridge_seat_points_for_bake),
        )
    
if __name__ == "__main__":
    bake_result = main("initial")
    bake_keys = bake_result[0][0]
    bake_objs = bake_result[0][1]
    bake_keys2 = bake_result[1][0]
    bake_objs2 = bake_result[1][1]
    bake_keys3 = bake_result[2][0]
    bake_objs3 = bake_result[2][1]
    # points, breps = main("initial", debug=True)
    # bake_keys, bake_objs = main("initial", debug=False)
