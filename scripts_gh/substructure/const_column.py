import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd
from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.pier_schemas import (
    ColumnInfo,
    InputPierInfo,
    PierTopInfo,
    PierTopSurfInfo,
)
from my_project.config.util_schemas import (
    LocalOffset,
    Octagon_Corners,
    Point2D,
    Point3D,
    Square_and_center_Corners,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_planer_srf_from_points,
    join_breps_or_raise,
)
from my_project.utils.geometry_gh.transform import (
    offset_point_in_frame,
    place_obj,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def get_ref_min_Uedge_offset(
    reference_offset: LocalOffset, # minus
    x_slope: float,
) -> float:
    return reference_offset.x * x_slope / 100 # %で与えられているので100で割る。reference_offset.xはマイナスの値である。もしx_slopeが正なら返り値はマイナスになる

# まずは上り線側中心点を00とするローカル座標で各点の座標を求める。中心は山形に飛び出ている（ｚは端部が０）
def get_pier_top_surf_corners(
    pier_top_surf_info: PierTopSurfInfo,
    UD_x: float,
) -> Square_and_center_Corners:
    width_y = pier_top_surf_info.width_y / 2
    UC2D = Point2D(0,0)
    DC2D = Point2D(UD_x, 0)
    UT2D = Point2D(0, width_y)
    DT2D = Point2D(UD_x, width_y)
    UN2D = Point2D(0, -width_y)
    DN2D = Point2D(UD_x, -width_y)
    x_slope = pier_top_surf_info.u2d_slope.value
    y_slope = pier_top_surf_info.crown_slope.value
    Uedge_z = 0
    Dedge_z = Uedge_z - UD_x * x_slope / 100 # %で与えられているので100で割る。Uのほうが高い場合正のスロープ。
    UC_z = Uedge_z - width_y * y_slope / 100 # 山形
    DC_z = Dedge_z - width_y * y_slope / 100
    return Square_and_center_Corners(
        UC = Point3D(UC2D.x, UC2D.y, UC_z),
        DC = Point3D(DC2D.x, DC2D.y, DC_z),
        UT = Point3D(UT2D.x, UT2D.y, Uedge_z),
        DT = Point3D(DT2D.x, DT2D.y, Dedge_z),
        UN = Point3D(UN2D.x, UN2D.y, Uedge_z),
        DN = Point3D(DN2D.x, DN2D.y, Dedge_z),
    )

def get_column_centers(
    num_columns: int,
    piertop_info: PierTopInfo,
    column_info: ColumnInfo,
) -> list[Point2D]:
    column_centers = []
    offset_x = piertop_info.u_side_x.x + column_info.inner_x / 2
    for i in range(num_columns):
        column_center = Point2D(x=offset_x, y=0)
        column_centers.append(column_center)
        if i < num_columns - 1:
            offset_x += column_info.inner_x + piertop_info.between_columns_x[i].x
    return column_centers

def get_column_2Dcorners(
    column_info: ColumnInfo,
    column_center: list[Point2D],
) -> list[Point2D]:
    x_ou = column_info.outer_x / 2
    x_in = column_info.inner_x / 2
    y_ou = column_info.outer_y / 2
    y_in = column_info.inner_y / 2
    offset_xs = [-x_ou, -x_in, -x_in, -x_ou, x_ou, x_in, x_in, x_ou]
    offset_ys = [y_in, y_ou, -y_ou, -y_in, -y_in, -y_ou, y_ou, y_in]
    center_x = column_center.x
    return [
        Point2D(
            x = center_x + offset_x,
            y = offset_y,
        )
        for offset_x, offset_y in zip(offset_xs, offset_ys)
    ]


def get_column_bottom_corners(
    column_2Dcorners: list[Point2D],
    ref_mi_Uedge_offset: float, # Uのほうが高い時、負の値。
    foundation_offset: LocalOffset,
) -> Octagon_Corners:
    z = ref_mi_Uedge_offset + foundation_offset.z # 基礎まで落とす。Uedge-ref がref_z_offset, 基礎-refがfoundation_offset.z（負値）
    return Octagon_Corners(
        UTT = Point3D(column_2Dcorners[0].x, column_2Dcorners[0].y, z),
        UTN = Point3D(column_2Dcorners[1].x, column_2Dcorners[1].y, z),
        UNT = Point3D(column_2Dcorners[2].x, column_2Dcorners[2].y, z),
        UNN = Point3D(column_2Dcorners[3].x, column_2Dcorners[3].y, z),
        DNN = Point3D(column_2Dcorners[4].x, column_2Dcorners[4].y, z),
        DNT = Point3D(column_2Dcorners[5].x, column_2Dcorners[5].y, z),
        DTN = Point3D(column_2Dcorners[6].x, column_2Dcorners[6].y, z),
        DTT = Point3D(column_2Dcorners[7].x, column_2Dcorners[7].y, z),
    )

def get_column_top_corners(
    column_2Dcorners: list[Point2D],
    ab_z: float, #梁_上z
    bl_z: float, #梁_下z
    x_slope: float,
    d_cut: bool,
    u_cut: bool,
) -> Octagon_Corners:
    if d_cut:
        d_cut_z = ab_z + bl_z
    else:
        d_cut_z = ab_z
    if u_cut:
        u_cut_z = ab_z + bl_z
    else:
        u_cut_z = ab_z
    return Octagon_Corners(
        UTT = Point3D(column_2Dcorners[0].x, column_2Dcorners[0].y, 0 - ab_z - column_2Dcorners[0].x * x_slope / 100),
        UTN = Point3D(column_2Dcorners[1].x, column_2Dcorners[1].y, 0 - u_cut_z - column_2Dcorners[1].x * x_slope / 100),
        UNT = Point3D(column_2Dcorners[2].x, column_2Dcorners[2].y, 0 - u_cut_z - column_2Dcorners[2].x * x_slope / 100),
        UNN = Point3D(column_2Dcorners[3].x, column_2Dcorners[3].y, 0 - ab_z - column_2Dcorners[3].x * x_slope / 100),
        DNN = Point3D(column_2Dcorners[4].x, column_2Dcorners[4].y, 0 - ab_z - column_2Dcorners[4].x * x_slope / 100),
        DNT = Point3D(column_2Dcorners[5].x, column_2Dcorners[5].y, 0 - d_cut_z - column_2Dcorners[5].x * x_slope / 100),
        DTN = Point3D(column_2Dcorners[6].x, column_2Dcorners[6].y, 0 - d_cut_z - column_2Dcorners[6].x * x_slope / 100),
        DTT = Point3D(column_2Dcorners[7].x, column_2Dcorners[7].y, 0 - ab_z - column_2Dcorners[7].x * x_slope / 100),
    )


def const_columns(
    column_centers: list[Point2D],
    column_info: ColumnInfo,
    x_slope: float,
    ab_z: float, #梁_上z
    bl_z: float, #梁_下z
    ref_min_Uedge_offset: float,
    foundation_offset: LocalOffset,
    d_cut_list: list[bool],
    u_cut_list: list[bool],
) -> list[rg.Brep]:
    columns = []
    column_top_corners_list = [] # 柱のコーナーの点を保存しておく
    column_bottom_corners_list = [] # 柱のコーナーの点を保存しておく
    for column_center, d_cut, u_cut in zip(column_centers, d_cut_list, u_cut_list):
        column_2Dcorners = get_column_2Dcorners(column_info, column_center)
        column_top_corners = get_column_top_corners(column_2Dcorners, ab_z, bl_z, x_slope, d_cut, u_cut)
        column_bottom_corners = get_column_bottom_corners(column_2Dcorners, ref_min_Uedge_offset, foundation_offset)
        column_top_corners_list.append(column_top_corners)
        column_bottom_corners_list.append(column_bottom_corners)
        def get_column_corners_list(column_corners: Octagon_Corners) -> list[Point3D]:
            return [
                column_corners.UTT,
                column_corners.UTN,
                column_corners.UNT,
                column_corners.UNN,
                column_corners.DNN,
                column_corners.DNT,
                column_corners.DTN,
                column_corners.DTT,
            ] 
        column_bottom_corners_l = get_column_corners_list(column_bottom_corners)
        column_top_corners_l = get_column_corners_list(column_top_corners)

        column_srfs = []
        # 底面
        column_bottom = const_planer_srf_from_points(column_bottom_corners_l)
        column_srfs.append(column_bottom)
        # 側面
        for i in range(8):
            corner1 = column_bottom_corners_l[i]
            corner2 = column_bottom_corners_l[(i+1)%8]
            corner3 = column_top_corners_l[(i+1)%8]
            corner4 = column_top_corners_l[i]
            side = const_planer_srf_from_points([corner1, corner2, corner3, corner4])
            column_srfs.append(side)
        # 上面
        U_column_top = const_planer_srf_from_points([column_top_corners.UTT, column_top_corners.UTN, column_top_corners.UNT, column_top_corners.UNN])
        D_column_top = const_planer_srf_from_points([column_top_corners.DNN, column_top_corners.DNT, column_top_corners.DTN, column_top_corners.DTT])
        C_column_top = const_planer_srf_from_points([column_top_corners.UTT, column_top_corners.UNN, column_top_corners.DNN, column_top_corners.DTT])
        column_srfs.extend([U_column_top, D_column_top, C_column_top])
        joined_brep = join_breps_or_raise(column_srfs, context="pier column")
        columns.append(joined_brep)
    return columns, column_top_corners_list, column_bottom_corners_list

def get_each_column(
    input_pier_info: InputPierInfo,
):
    # 橋脚のローカル2D座標系を求める
    point_u = input_pier_info.points_for_vector.point_u
    point_d = input_pier_info.points_for_vector.point_d
    frame_2D = get_frame_2D(
        point_u=Point2D(x=point_u.x, y=point_u.y),
        point_d=Point2D(x=point_d.x, y=point_d.y),
        y_direction="UP" # →がx、↑がyとする。
    )

    # ゼロ点を橋座面の基準点に合わせる
    zero_point = offset_point_in_frame(
        point=input_pier_info.piertop_surf.reference_point,
        local_offset=input_pier_info.piertop_surf.reference_offset,
        frame_2D=frame_2D,
    )
    ref_min_Uedge_offset = get_ref_min_Uedge_offset(
        reference_offset=input_pier_info.piertop_surf.reference_offset,
        x_slope=input_pier_info.piertop_surf.u2d_slope.value,
    )
    zero_point_world_z = input_pier_info.piertop_surf.reference_point.z - ref_min_Uedge_offset
    zero_point = Point3D(x=zero_point.x, y=zero_point.y, z=zero_point_world_z)
    print(f"zero_point: {zero_point}")
    # 柱の数
    num_columns = len(input_pier_info.piertop.between_columns_x) + 1

    # 橋座面の点を求める
    UD_x = input_pier_info.piertop.u_side_x.x + input_pier_info.piertop.d_side_x.x + input_pier_info.column.inner_x * num_columns + sum(between_column_x.x for between_column_x in input_pier_info.piertop.between_columns_x)
    piertop_surf_corners = get_pier_top_surf_corners(
        pier_top_surf_info=input_pier_info.piertop_surf,
        UD_x=UD_x,
    )

    # 橋座面の点はワールドに変換して保存しておく
    world_piertop_surf_corners = Square_and_center_Corners(
        UC = const_3Dpoint(place_obj(obj=piertop_surf_corners.UC, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
        DC = const_3Dpoint(place_obj(obj=piertop_surf_corners.DC, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
        UT = const_3Dpoint(place_obj(obj=piertop_surf_corners.UT, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
        DT = const_3Dpoint(place_obj(obj=piertop_surf_corners.DT, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
        UN = const_3Dpoint(place_obj(obj=piertop_surf_corners.UN, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
        DN = const_3Dpoint(place_obj(obj=piertop_surf_corners.DN, local_origin=Point3D(0,0,0), world_origin=zero_point, frame_2D=frame_2D)),
    )

    # 各柱の中心点
    column_centers = get_column_centers(
        num_columns=num_columns,
        piertop_info=input_pier_info.piertop,
        column_info=input_pier_info.column,
    )
    # 柱のbrepと柱のコーナーの点
    u_cuts = [True for _ in range(num_columns)]
    d_cuts = [True for _ in range(num_columns)]
    if pd.isna(input_pier_info.piertop.u_side_x.pier_top_x_type):
        u_cuts[0] = False
    if pd.isna(input_pier_info.piertop.d_side_x.pier_top_x_type):
        d_cuts[-1] = False
    columns, top_corners, bottom_corners = const_columns(
        column_centers=column_centers,
        column_info=input_pier_info.column,
        x_slope=input_pier_info.piertop_surf.u2d_slope.value,
        ab_z=input_pier_info.piertop.heights.top_z,
        bl_z=input_pier_info.piertop.heights.bottom_z,
        ref_min_Uedge_offset=ref_min_Uedge_offset,
        foundation_offset=input_pier_info.footing.reference_offset if not pd.isna(input_pier_info.footing) else input_pier_info.caisson.reference_offset,
        u_cut_list=u_cuts,
        d_cut_list=d_cuts,
    )
    columns_dict = {}
    column_top_corners_dict = {}
    column_bottom_corners_dict = {}
    world_columns_dict = {}
    for i, (column, top_corners, bottom_corners) in enumerate(zip(columns, top_corners, bottom_corners)):
        column_name = f"column_{i+1}"
        columns_dict[column_name] = column
        column_top_corners_dict[column_name] = top_corners
        column_bottom_corners_dict[column_name] = bottom_corners
        # 柱の部品はbakeするので、ワールド座標に変換して保存しておく
        world_columns_dict[column_name] = place_obj(
            obj=column,
            local_origin=Point3D(0,0,0),
            world_origin=zero_point,
            frame_2D=frame_2D,
        )
        

    return {
        "world_zero_point": zero_point,
        "frame_2D": frame_2D,
        "piertop_surf_corners": piertop_surf_corners,
        "column_top_corners": column_top_corners_dict,
        "column_bottom_corners": column_bottom_corners_dict,
    }, world_columns_dict, world_piertop_surf_corners

def main(initial_or_final: str):
    DIR = get_output_dir(initial_or_final)

    indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}.pickle")

    local_dict = {}
    world_dict = {}
    world_columns_dict_for_bake = {}

    for pier_name, indiv_info in indiv_infos.items():
        local_each_dict, world_columns, world_piertop_surf_corners = get_each_column(
            input_pier_info=indiv_info,
        )
        local_dict[pier_name] = local_each_dict # ここはpickel用
        world_dict[pier_name] = {
            "frame_2D" : local_each_dict["frame_2D"],
            "top_corners" : world_piertop_surf_corners
        } # ここはpickel用
        world_columns_dict_for_bake[pier_name] = world_columns # ここはbake用
    
    # ローカルを全部pickelに保存
    save_json_and_pickle(
        data = local_dict,
        folder_path = DIR,
        name = f"{Filenames.LOCAL}_{Filenames.PIER}_{Filenames.COLUMN}",
    )
    save_json_and_pickle(
        data = world_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.PIER}_{Filenames.TOP}_{Filenames.POINTS}",
    )
    # ワールドの柱をbake用にフラット化して保存
    column_flatten_dict_for_bake = flatten_any(world_columns_dict_for_bake)
    items = list(column_flatten_dict_for_bake.items())
    keys = [k for k, _ in items]
    values = [v for _, v in items]

    return keys, values

if __name__ == "__main__":
    bake_keys, bake_objs = main("initial")
