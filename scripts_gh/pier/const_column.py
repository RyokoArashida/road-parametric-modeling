
import pandas as pd
import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.input_pier_schemas import (
    ColumnInfo,
    InputPierInfo,
    PierTopInfo,
    PierTopSurfInfo,
)
from my_project.config.model_pier_schemas import (
    Local_ColumnModel,
    Local_PierTopSurfModel,
)
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    Point2D,
    Point3D,
    Vector2D,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry import (
    extrude_curve,
    get_intersection_polylines,
    get_plane_from_points,
    get_slope_plane,
    offset_point_in_frame,
    place_obj,
    sort_points_clockwise_from_upper_right,
    split_brep_and_keep_by_centroid_z,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle
from my_project.utils.lines import conset_closed_polycurve_obj
from my_project.utils.proprocess import normalize


def get_frame_2D(point_u: Point2D, point_d: Point2D) -> Frame2D:
    # U -> D のベクトルをx軸とする
    raw_x = Vector2D(
        x=point_d.x - point_u.x,
        y=point_d.y - point_u.y
    )
    x_axis = normalize(raw_x)
    y_axis = Vector2D(
        x=-x_axis.y,
        y=x_axis.x,
    ) # x軸に対して反時計回りに90度回転させるとy軸になる
    return Frame2D(
        x_axis=x_axis,
        y_axis=y_axis,
    )

def get_ref_min_Uedge_offset(
    reference_offset: LocalOffset, # minus
    x_slope: float,
) -> float:
    return reference_offset.x * x_slope / 100 # %で与えられているので100で割る。reference_offset.xはマイナスの値である。もしx_slopeが正なら返り値はマイナスになる

# まずは上り線側中心点を00とするローカル座標で各点の座標を求める。中心は山形に飛び出ている（ｚは端部が０）
def get_pier_top_surf_corners(
    pier_top_surf_info: PierTopSurfInfo,
    UD_x: float,
) -> Local_PierTopSurfModel:
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
    return Local_PierTopSurfModel(
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
) -> Local_ColumnModel:
    z = ref_mi_Uedge_offset + foundation_offset.z # 基礎まで落とす。Uedge-ref がref_z_offset, 基礎-refがfoundation_offset.z（負値）
    return Local_ColumnModel(
        UTT = Point3D(column_2Dcorners[0].x, column_2Dcorners[0].y, z),
        UTN = Point3D(column_2Dcorners[1].x, column_2Dcorners[1].y, z),
        UNT = Point3D(column_2Dcorners[2].x, column_2Dcorners[2].y, z),
        UNN = Point3D(column_2Dcorners[3].x, column_2Dcorners[3].y, z),
        DNN = Point3D(column_2Dcorners[4].x, column_2Dcorners[4].y, z),
        DNT = Point3D(column_2Dcorners[5].x, column_2Dcorners[5].y, z),
        DTN = Point3D(column_2Dcorners[6].x, column_2Dcorners[6].y, z),
        DTT = Point3D(column_2Dcorners[7].x, column_2Dcorners[7].y, z),
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
        center_3D_z = - column_center.x * x_slope / 100 - ab_z # 柱の高さはUedgeを基準としている
        column_2Dcorners = get_column_2Dcorners(column_info, column_center)
        column_bottom_corners = get_column_bottom_corners(column_2Dcorners, ref_min_Uedge_offset, foundation_offset)
        # まずは一番高いところまでの柱を作る
        def get_column_corners_list(column_corners: Local_ColumnModel) -> list[Point3D]:
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
        column_bottom_corners = get_column_corners_list(column_bottom_corners)
        z_max_top = center_3D_z + 1000 # とりあえず十分大きい値を足して柱の上面のzとする。後でsplitして調整する。
        z_max_bottom = max(corner.z for corner in column_bottom_corners) # 本当は全部同じ
        print(f"z_max_top: {z_max_top}, z_max_bottom: {z_max_bottom}")
        rough_column = extrude_curve(
            obj=conset_closed_polycurve_obj(column_bottom_corners),
            vector=rg.Vector3d(0, 0, z_max_top - z_max_bottom),
            cap=True,
        )
        #上部を削っていく。
        cutter_plane = get_slope_plane(
            point=Point3D(column_center.x, column_center.y, center_3D_z),
            slope=-x_slope, # xが増えるとzが減るのでマイナス
            XY="X",
        )
        column_after_cut = split_brep_and_keep_by_centroid_z(rough_column, cutter_plane, keep="lower")
        points_after_cut = get_intersection_polylines(rough_column, cutter_plane)

        def get_local_column_model_from_points(
            points: list[rg.Point3d],
        ) -> Local_ColumnModel:
            if len(points) != 8:
                raise ValueError(f"柱のコーナーは8点必要ですが、{len(points)}点が与えられました。{points}")
            # 点をX降順、Y降順でソートする。Xが同じならYが大きいほうが先に出てくる
            points_sorted = sort_points_clockwise_from_upper_right(points, center=column_center)
            column_corners = Local_ColumnModel(
                DTT = Point3D(points_sorted[0].X, points_sorted[0].Y, points_sorted[0].Z),
                DTN = Point3D(points_sorted[1].X, points_sorted[1].Y, points_sorted[1].Z),
                DNT = Point3D(points_sorted[2].X, points_sorted[2].Y, points_sorted[2].Z),
                DNN = Point3D(points_sorted[3].X, points_sorted[3].Y, points_sorted[3].Z),
                UNN = Point3D(points_sorted[4].X, points_sorted[4].Y, points_sorted[4].Z),
                UNT = Point3D(points_sorted[5].X, points_sorted[5].Y, points_sorted[5].Z),
                UTN = Point3D(points_sorted[6].X, points_sorted[6].Y, points_sorted[6].Z),
                UTT = Point3D(points_sorted[7].X, points_sorted[7].Y, points_sorted[7].Z),
            )
            return column_corners

        corners_after_cut = get_local_column_model_from_points(points_after_cut)
        # U側を削る
        if u_cut:
            U_p1 = corners_after_cut.UTT
            U_p2 = corners_after_cut.UNN #この2つはそのまま使われる
            U_p3 = Point3D(corners_after_cut.UTN.x, corners_after_cut.UTN.y, corners_after_cut.UTN.z - bl_z) # 内側の点は削る
            cutter_plane_U = get_plane_from_points(U_p1, U_p2, U_p3)
            column_after_cutU = split_brep_and_keep_by_centroid_z(column_after_cut, cutter_plane_U, keep="lower")
            column_after_cut = column_after_cutU
        # # D側を削る
        if d_cut:
            D_p1 = corners_after_cut.DTT
            D_p2 = corners_after_cut.DNN #この2つはそのまま使われる
            D_p3 = Point3D(corners_after_cut.DTN.x, corners_after_cut.DTN.y, corners_after_cut.DTN.z - bl_z) # 内側の点は削る
            cutter_plane_D = get_plane_from_points(D_p1, D_p2, D_p3)
            column_after_cutD = split_brep_and_keep_by_centroid_z(column_after_cut, cutter_plane_D, keep="lower")
            column_after_cut = column_after_cutD

        points = [v.Location for v in column_after_cut.Vertices]
        if len(points) != 16:
            raise ValueError(f"柱の頂点は16点必要ですが、{len(points)}点が与えられました。")
        bottom_points = sorted(points, key=lambda p: p.Z)[:8] # Zが低い順に並べて下位8点を取る
        top_points = sorted(points, key=lambda p: p.Z, reverse=True)[:8] # Zが高い順に並べて上位8点を取る
        bottom_corners = get_local_column_model_from_points(bottom_points)
        top_corners = get_local_column_model_from_points(top_points)
        columns.append(column_after_cut)
        column_bottom_corners_list.append(bottom_corners)
        column_top_corners_list.append(top_corners)
    return columns, column_top_corners_list, column_bottom_corners_list

def get_each_column(
    input_pier_info: InputPierInfo,
) -> dict[str, rg.Brep]:
    # 橋脚のローカル2D座標系を求める
    point_u = input_pier_info.points_for_vector.point_u
    point_d = input_pier_info.points_for_vector.point_d
    frame_2D = get_frame_2D(
        point_u=Point2D(x=point_u.x, y=point_u.y),
        point_d=Point2D(x=point_d.x, y=point_d.y),
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
        # 柱の部品だけはbakeするので、ワールド座標に変換して保存しておく
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
    }, world_columns_dict

def main(initial_or_final: str):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}.pickle")
    common_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.COMMON}.pickle")

    local_dict = {}
    world_columns_dict_for_bake = {}

    for pier_name, indiv_info in indiv_infos.items():
        bridge_type = indiv_info.type
        common_info = common_infos[bridge_type]
        local_each_dict, world_columns = get_each_column(
            input_pier_info=indiv_info,
            # input_common_info=common_info,
        )
        local_dict[pier_name] = local_each_dict # ここはpickel用
        world_columns_dict_for_bake[pier_name] = world_columns # ここはbake用
    
    # ローカルを全部pickelに保存
    save_json_and_pickle(
        data = local_dict,
        folder_path = DIR,
        name = f"{Filenames.LOCAL}_{Filenames.PIER}_{Filenames.COLUMN}",
    )
    column_flatten_dict_for_bake = flatten_any(world_columns_dict_for_bake)
    return column_flatten_dict_for_bake

if __name__ == "__main__":
    bake_dict = main("initial")
