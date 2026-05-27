from typing import Any

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd
from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.pier_schemas import (
    CommonPierInfo,
    InputPierInfo,
)
from my_project.config.util_schemas import Octagon_Corners, Point3D
from my_project.utils.geometry_gh.const import (
    const_arc_from_three_points,
    const_arc_half_from_center_edge_points,
    const_extrude_brep_from_curve,
    const_planer_srf_from_points,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
)
from my_project.utils.geometry_gh.intersect import split_two_surfaces
from my_project.utils.geometry_gh.transform import place_obj
from my_project.utils.io import load_from_pickle


def get_column_top_srfs(
    column_top_corners: Octagon_Corners
):
    col_U_srf = const_planer_srf_from_points([
        column_top_corners.UTT,
        column_top_corners.UTN,
        column_top_corners.UNT,
        column_top_corners.UNN
    ])
    col_D_srf = const_planer_srf_from_points([
        column_top_corners.DTT,
        column_top_corners.DTN,
        column_top_corners.DNT,
        column_top_corners.DNN
    ])
    col_C_srf = const_planer_srf_from_points([
        column_top_corners.UTT,
        column_top_corners.UNN,
        column_top_corners.DNN,
        column_top_corners.DTT,
    ])
    return col_U_srf, col_C_srf, col_D_srf

def get_slope_or_curve_edge_srf(
    edge_type: str,
    hri_TT: Point3D,
    hri_TN: Point3D,
    hri_NT: Point3D,
    hri_NN: Point3D,
    edge_TT: Point3D,
    edge_TN: Point3D,
    edge_NT: Point3D,
    edge_NN: Point3D,
    tangent_dir: str # edgeがどっち向きにあるか
):
    if edge_type == "直線": # 端部は絶対にplanにならない
        TT_curve = const_polycurve_obj([hri_TT, edge_TT])
        TN_curve = const_polycurve_obj([hri_TN, edge_TN])
        NT_curve = const_polycurve_obj([hri_NT, edge_NT])
        NN_curve = const_polycurve_obj([hri_NN, edge_NN])

    elif edge_type == "曲線": # 端部は絶対にplanにならない
        TT_curve = const_arc_half_from_center_edge_points(
            center = hri_TT,
            edge = edge_TT,
            tangent_dir= tangent_dir,
        )
        TN_curve = const_arc_half_from_center_edge_points(
            center = hri_TN,
            edge = edge_TN,
            tangent_dir= tangent_dir,
        )
        NT_curve = const_arc_half_from_center_edge_points(
            center = hri_NT,
            edge = edge_NT,
            tangent_dir= tangent_dir,
        )
        NN_curve = const_arc_half_from_center_edge_points(
            center = hri_NN,
            edge = edge_NN,
            tangent_dir= tangent_dir,
        )

    T_srf = const_srf_from_2crvs([TT_curve, TN_curve])
    C_srf = const_srf_from_2crvs([TN_curve, NT_curve])
    N_srf = const_srf_from_2crvs([NT_curve, NN_curve])
    return T_srf, C_srf, N_srf

def get_top_and_edge_srf(
    UD: str,
    edge_type: str,
    edge_x: float,
    edge_max: bool,
    slope_max_x: float,
    curve_max_x: float,
    edge_ab_z: float,
    edge_bl_z: float,
    edge_T_point: Point3D,
    edge_N_point: Point3D,
    edge_C_point: Point3D,
    col_TT_point: Point3D,
    col_TN_point: Point3D,
    col_NT_point: Point3D,
    col_NN_point: Point3D,
    T_rough_top_srf: rg.Brep,
    N_rough_top_srf: rg.Brep,
):
    srfs = []
    T_top_srf = T_rough_top_srf
    N_top_srf = N_rough_top_srf
    if pd.isna(edge_type):
        def get_top_and_edge_srf_noedge(
            top_srf: rg.Brep,
            corner_point: Point3D,
            edge_point1: Point3D,
            edge_point2: Point3D,
        ):
            edge_srf_extend = const_extrude_brep_from_curve(
                crv = const_polycurve_obj([edge_point1, edge_point2]),
                vector = rg.Vector3d(0,0,edge_ab_z + 10000), # 10000は適当な大きい数値
                cap=False,
            )
            top_srf_split, edge_srf_split = split_two_surfaces(
                srf_a = top_srf,
                srf_b = edge_srf_extend,
            )
            top_centers = [rg.AreaMassProperties.Compute(srf).Centroid for srf in top_srf_split]
            edge_centers = [rg.AreaMassProperties.Compute(srf).Centroid for srf in edge_srf_split]

            # topのほうはcorner_pointに遠い方を残す（角を落とすイメージ）
            top_distances = [const_point_obj(corner_point).DistanceTo(center) for center in top_centers]
            top_srf = top_srf_split[top_distances.index(max(top_distances))]
            # edgeのほうはzが最小のものを残す（上を切っている）
            edge_srf = edge_srf_split[edge_centers.index(min(edge_centers, key=lambda c: c.Z))]
            return top_srf, edge_srf
        
        T_top_srf, T_edge_srf = get_top_and_edge_srf_noedge(
            top_srf = T_rough_top_srf,
            corner_point = edge_T_point,
            edge_point1 = col_TT_point,
            edge_point2 = col_TN_point,
        )
        N_top_srf, N_edge_srf = get_top_and_edge_srf_noedge(
            top_srf = N_rough_top_srf,
            corner_point = edge_N_point,
            edge_point1 = col_NN_point,
            edge_point2 = col_NT_point,
        )
        srfs.append(T_edge_srf)
        srfs.append(N_edge_srf)

    else:
        edge_top_T = edge_T_point
        edge_top_C = edge_C_point
        edge_top_N = edge_N_point
        edge_bottom_TT = Point3D(edge_top_T.x, edge_top_T.y, edge_top_T.z - edge_ab_z)
        edge_bottom_TN = Point3D(edge_top_T.x, col_TN_point.y, edge_top_T.z - edge_ab_z - edge_bl_z)
        edge_bottom_NT = Point3D(edge_top_N.x, col_NT_point.y, edge_top_N.z - edge_ab_z - edge_bl_z) # edge_top_TとNのxは本当は同じ
        edge_bottom_NN = Point3D(edge_top_N.x, edge_top_N.y, edge_top_N.z - edge_ab_z)
        edge_srf = const_planer_srf_from_points([
            edge_top_N,
            edge_top_C,
            edge_top_T,
            edge_bottom_TT,
            edge_bottom_TN,
            edge_bottom_NT,
            edge_bottom_NN,
        ])
        srfs.append(edge_srf)

        hri_len = 0
        if edge_type == "直線":
            max_x = slope_max_x
        elif edge_type == "曲線":
            max_x = curve_max_x
        if edge_x > max_x and edge_max:
            hri_len = edge_x - max_x

        edge_bottom_TT_hri = edge_bottom_TT
        edge_bottom_TN_hri = edge_bottom_TN
        edge_bottom_NT_hri = edge_bottom_NT
        edge_bottom_NN_hri = edge_bottom_NN
        if hri_len > 0:
            hri_x = hri_len if UD == "U" else -1 * hri_len
            edge_bottom_crv = const_polycurve_obj([edge_bottom_TT, edge_bottom_TN, edge_bottom_NT, edge_bottom_NN])
            hri_bottom_srf = const_extrude_brep_from_curve(
                crv = edge_bottom_crv,
                vector = rg.Vector3d(hri_x, 0, 0),
                cap=False,
            )
            srfs.append(hri_bottom_srf)

            edge_bottom_TT_hri= Point3D(edge_bottom_TT.x + hri_x, edge_bottom_TT.y, edge_bottom_TT.z)
            edge_bottom_TN_hri = Point3D(edge_bottom_TN.x + hri_x, edge_bottom_TN.y, edge_bottom_TN.z)
            edge_bottom_NT_hri = Point3D(edge_bottom_NT.x + hri_x, edge_bottom_NT.y, edge_bottom_NT.z)
            edge_bottom_NN_hri = Point3D(edge_bottom_NN.x + hri_x, edge_bottom_NN.y, edge_bottom_NN.z)

        edge_T_srf, edge_C_srf, edge_N_srf = get_slope_or_curve_edge_srf(
            edge_type = edge_type,
            hri_TT = edge_bottom_TT_hri,
            hri_TN = edge_bottom_TN_hri,
            hri_NT = edge_bottom_NT_hri,
            hri_NN = edge_bottom_NN_hri,
            edge_TT = col_TT_point,
            edge_TN = col_TN_point,
            edge_NT = col_NT_point,
            edge_NN = col_NN_point,
            tangent_dir = "Xplus" if UD == "U" else "Xminus",
        )

        srfs.extend([edge_T_srf, edge_C_srf, edge_N_srf])
    return srfs, T_top_srf, N_top_srf

def get_between_srf(
    edge_type: str,
    edge_x: float,
    slope_max_x: float,
    curve_max_x: float,
    ab_col_z: float,
    ab_mid_z: float,
    bl_z: float,
    Ucol_TT_point: Point3D,
    Ucol_TN_point: Point3D,
    Ucol_NT_point: Point3D,
    Ucol_NN_point: Point3D,
    Dcol_TT_point: Point3D,
    Dcol_TN_point: Point3D,
    Dcol_NT_point: Point3D,
    Dcol_NN_point: Point3D,
):
    btw_srfs = []
    if edge_type == "直線":
        max_x = slope_max_x
    elif edge_type == "曲線":
        max_x = curve_max_x

    z_gap = ab_col_z - ab_mid_z # 正になるはず

    def get_short_crv(U_point, D_point):
        mid_point = Point3D((U_point.x + D_point.x)/2, (U_point.y + D_point.y)/2, (U_point.z + D_point.z)/2 + z_gap)
        if edge_type == "直線":
            crv = const_polycurve_obj([U_point, mid_point, D_point])
            U_crv = const_polycurve_obj([U_point, mid_point])
            D_crv = const_polycurve_obj([mid_point, D_point])
        elif edge_type == "曲線":
            crv = const_arc_from_three_points(U_point, mid_point, D_point)
            ok, t_mid = crv.ClosestPoint(const_point_obj(mid_point))
            if not ok:
                raise Exception("mid point がカーブ上にない")
            domain = crv.Domain
            U_crv = crv.Trim(domain.T0, t_mid)
            D_crv = crv.Trim(t_mid, domain.T1)
        return crv, U_crv, D_crv, mid_point

    if edge_x <= max_x * 2:
        # 本来はいろいろあるみたいだが、とりあえず両方の中間点からgapだけ上がったところを通ることにする。
        TT_crv, _, _, _ = get_short_crv(Ucol_TT_point, Dcol_TT_point)
        TN_crv, _, _, _ = get_short_crv(Ucol_TN_point, Dcol_TN_point)
        NT_crv, _, _, _ = get_short_crv(Ucol_NT_point, Dcol_NT_point)
        NN_crv, _, _, _ = get_short_crv(Ucol_NN_point, Dcol_NN_point)
        T_srf = const_srf_from_2crvs([TT_crv, TN_crv])
        C_srf = const_srf_from_2crvs([TN_crv, NT_crv])
        N_srf = const_srf_from_2crvs([NT_crv, NN_crv])
        btw_srfs.extend([T_srf, C_srf, N_srf])

    else:
        hri_len = edge_x - max_x * 2
        # 本来はいろいろあるみたいだが、とりあえずhriを引いた位置に仮想的につくり、gapだけ上がったところを通ることにして、その中間に水平な面をつくることにする。
        Dcol_TT_point_moved = Point3D(Dcol_TT_point.x - hri_len, Dcol_TT_point.y, Dcol_TT_point.z)
        Dcol_TN_point_moved = Point3D(Dcol_TN_point.x - hri_len, Dcol_TN_point.y, Dcol_TN_point.z)
        Dcol_NT_point_moved = Point3D(Dcol_NT_point.x - hri_len, Dcol_NT_point.y, Dcol_NT_point.z)
        Dcol_NN_point_moved = Point3D(Dcol_NN_point.x - hri_len, Dcol_NN_point.y, Dcol_NN_point.z)
        _, UTTcrv, DTTcrv, TTmid = get_short_crv(Ucol_TT_point, Dcol_TT_point_moved)
        _, UTNcrv, DTNcrv, TNmid = get_short_crv(Ucol_TN_point, Dcol_TN_point_moved)
        _, UNTcrv, DNTcrv, NTmid = get_short_crv(Ucol_NT_point, Dcol_NT_point_moved)
        _, UNNcrv, DNNcrv, NNmid = get_short_crv(Ucol_NN_point, Dcol_NN_point_moved)
        # D側のカーブをhri分移動させる
        def get_three_crvs(Ucrv, Dcrv, mid, hri_len):
            Dcrv_moved = Dcrv.DuplicateCurve()
            Dcrv_moved.Translate(rg.Vector3d(hri_len, 0, 0))
            mid_moved = Point3D(mid.x + hri_len, mid.y, mid.z)
            mid_crv = const_polycurve_obj([mid, mid_moved])
            return Ucrv, mid_crv, Dcrv_moved
        UTTcrv, TTmid_crv, DTTcrv_moved = get_three_crvs(UTTcrv, DTTcrv, TTmid, hri_len)
        UTNcrv, TNmid_crv, DTNcrv_moved = get_three_crvs(UTNcrv, DTNcrv, TNmid, hri_len)
        UNTcrv, NTmid_crv, DNTcrv_moved = get_three_crvs(UNTcrv, DNTcrv, NTmid, hri_len)
        UNNcrv, NNmid_crv, DNNcrv_moved = get_three_crvs(UNNcrv, DNNcrv, NNmid, hri_len)
        UT_srf = const_srf_from_2crvs([UTTcrv, UTNcrv])
        UC_srf = const_srf_from_2crvs([UTNcrv, UNTcrv])
        UN_srf = const_srf_from_2crvs([UNTcrv, UNNcrv])
        hriT_srf = const_srf_from_2crvs([TTmid_crv, TNmid_crv])
        hriC_srf = const_srf_from_2crvs([TNmid_crv, NTmid_crv])
        hriN_srf = const_srf_from_2crvs([NTmid_crv, NNmid_crv])
        DT_srf = const_srf_from_2crvs([DTTcrv_moved, DTNcrv_moved])
        DC_srf = const_srf_from_2crvs([DTNcrv_moved, DNTcrv_moved])
        DN_srf = const_srf_from_2crvs([DNTcrv_moved, DNNcrv_moved])
        btw_srfs.extend([UT_srf, UC_srf, UN_srf, hriT_srf, hriC_srf, hriN_srf, DT_srf, DC_srf, DN_srf])

    return btw_srfs
            
def get_each_piertop(
    indiv_info: InputPierInfo,
    common_info: CommonPierInfo,
    column_info: dict[str, Any],
    tol: float = 0.01,
):
    if indiv_info.piertop.heights.top_z < tol:
        return [] # 梁がない場合は空のリストを返す

    piertop_corners = column_info["piertop_surf_corners"]
    column_top_corners = list(column_info["column_top_corners"].values())

    srfs = []

    T_rough_top_srf = const_planer_srf_from_points(
        [piertop_corners.UT, piertop_corners.DT, piertop_corners.DC, piertop_corners.UC]
    )
    N_rough_top_srf = const_planer_srf_from_points(
        [piertop_corners.UN, piertop_corners.DN, piertop_corners.DC, piertop_corners.UC]
    )

    for column_top_corner in column_top_corners:
        col_top_srfs = get_column_top_srfs(column_top_corner)
        srfs.extend(col_top_srfs)

    u_edge_srfs, T_rough_top_srf_U, N_rough_top_srf_U = get_top_and_edge_srf(
        UD="U",
        edge_type = indiv_info.piertop.u_side_x.pier_top_x_type,
        edge_x = indiv_info.piertop.u_side_x.x,
        edge_max= indiv_info.piertop.u_side_x.max,
        slope_max_x = common_info.max_piertop_x.max_slope_x,
        curve_max_x = common_info.max_piertop_x.max_curve_x,
        edge_ab_z = indiv_info.piertop.heights.top_U_z,
        edge_bl_z = indiv_info.piertop.heights.bottom_z,
        edge_T_point = column_info["piertop_surf_corners"].UT,
        edge_C_point = column_info["piertop_surf_corners"].UC,
        edge_N_point = column_info["piertop_surf_corners"].UN,
        col_TT_point = column_top_corners[0].UTT,
        col_TN_point = column_top_corners[0].UTN,
        col_NT_point = column_top_corners[0].UNT,
        col_NN_point = column_top_corners[0].UNN,
        T_rough_top_srf = T_rough_top_srf,
        N_rough_top_srf = N_rough_top_srf,
    )
    d_edge_srfs, T_top_srf, N_top_srf = get_top_and_edge_srf(
        UD="D",
        edge_type = indiv_info.piertop.d_side_x.pier_top_x_type,
        edge_x = indiv_info.piertop.d_side_x.x,
        edge_max = indiv_info.piertop.d_side_x.max,
        slope_max_x = common_info.max_piertop_x.max_slope_x,
        curve_max_x = common_info.max_piertop_x.max_curve_x,
        edge_ab_z = indiv_info.piertop.heights.top_D_z,
        edge_bl_z = indiv_info.piertop.heights.bottom_z,
        edge_T_point = column_info["piertop_surf_corners"].DT,
        edge_C_point = column_info["piertop_surf_corners"].DC,
        edge_N_point = column_info["piertop_surf_corners"].DN,
        col_TT_point = column_top_corners[-1].DTT,
        col_TN_point = column_top_corners[-1].DTN,
        col_NT_point = column_top_corners[-1].DNT,
        col_NN_point = column_top_corners[-1].DNN,
        T_rough_top_srf = T_rough_top_srf_U,
        N_rough_top_srf = N_rough_top_srf_U,
    )

    srfs.extend(u_edge_srfs)
    srfs.extend(d_edge_srfs)
    srfs.append(T_top_srf)
    srfs.append(N_top_srf)

    btw_infos = indiv_info.piertop.between_columns_x
    for i, btw_info in enumerate(btw_infos):
        U_column_top_corners = column_top_corners[i]
        D_column_top_corners = column_top_corners[i+1]
        btw_srfs = get_between_srf(
            edge_type = btw_info.pier_top_x_type,
            edge_x = btw_info.x,
            slope_max_x = common_info.max_piertop_x.max_slope_x,
            curve_max_x = common_info.max_piertop_x.max_curve_x,
            ab_col_z = indiv_info.piertop.heights.top_z,
            ab_mid_z = indiv_info.piertop.heights.mid_top_z,
            bl_z = indiv_info.piertop.heights.bottom_z,
            Ucol_TT_point = U_column_top_corners.DTT,
            Ucol_TN_point = U_column_top_corners.DTN,
            Ucol_NT_point = U_column_top_corners.DNT,
            Ucol_NN_point = U_column_top_corners.DNN,
            Dcol_TT_point = D_column_top_corners.UTT,
            Dcol_TN_point = D_column_top_corners.UTN,
            Dcol_NT_point = D_column_top_corners.UNT,
            Dcol_NN_point = D_column_top_corners.UNN,
        )
        srfs.extend(btw_srfs)
    return srfs

def main(initial_or_final: str, tol: float = 0.01):
    
    DIR = get_output_dir(initial_or_final)

    indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}.pickle")
    common_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.COMMON}.pickle")

    column_infos = load_from_pickle(DIR / f"{Filenames.LOCAL}_{Filenames.PIER}_{Filenames.COLUMN}.pickle")

    world_piertop_dict_for_bake = {}

    for pier_name, indiv_info in indiv_infos.items():
        bridge_type = indiv_info.type
        common_info = common_infos[bridge_type]
        column_info = column_infos[pier_name]

        srfs = get_each_piertop(
            indiv_info=indiv_info,
            common_info=common_info,
            column_info=column_info,
        )
        if len(srfs) == 0:
            print(f"{pier_name}のpiertopはありません")
            continue
        joined_brep = rg.Brep.JoinBreps(srfs, tol)
        if not joined_brep:
            ValueError(f"{pier_name}のpiertopは結合できませんでした。結合前のサーフェスの数: {len(srfs)}")
        elif len(joined_brep) != 1:
            ValueError(f"{pier_name}のpiertopは結合後のBrepが複数になりました。結合前のサーフェスの数: {len(srfs)} 結合後のBrepの数: {len(joined_brep)}")
        brep = joined_brep[0]
        brep_cap = brep.CapPlanarHoles(tol)
        if not brep_cap:
            ValueError(f"{pier_name}のpiertopは穴をふさげませんでした。結合前のサーフェスの数: {len(srfs)} 結合後のBrepの数: {len(joined_brep)}") 

        frame_2D = column_info["frame_2D"]
        world_zero_point = column_info["world_zero_point"]
        world_brep = place_obj(
            obj = brep_cap,
            local_origin=Point3D(0,0,0),
            world_origin=world_zero_point,
            frame_2D=frame_2D,
        )
        world_piertop_dict_for_bake[pier_name] = world_brep
        if not world_brep.IsSolid:
            print(f"{pier_name}のpiertopは閉じていません")
    items = world_piertop_dict_for_bake.items()
    keys = [k for k, _ in items]
    values = [v for _, v in items]

    return keys, values
        

if __name__ == "__main__":
    bake_keys, bake_objs = main("initial")
