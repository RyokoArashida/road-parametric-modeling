

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.input_abut_schemas import (
    BackwallInfo,
    BarrierCommonInfo,
    BarrierInfo,
    CaissonFoundationInfo,
    CommonAbutInfo,
    FootingInfo,
    InputAbutInfo,
    PileFoundationInfo,
    PointsForVector,
    SeatInfo,
    SlabSeatInfo,
    WaterTreatmentNotchInfo,
    WaterTreatmentWallInfo,
    WingInfo,
)
from my_project.config.util_schemas import (
    LocalOffset,
    MonoSlope,
    Point3D,
)
from my_project.utils.io import read_file_to_df, save_json_and_pickle
from my_project.utils.proprocess import get_coord_data, get_four_corners


def get_indiv_abut_info(
    param_row: pd.Series,
    coord_df: pd.DataFrame,
) -> InputAbutInfo:
    abut_name = param_row["全体_橋脚名"]
    abut_name_UD = None if pd.isna(param_row["全体_上下"]) else param_row["全体_上下"]
    abut_name_merge = abut_name + abut_name_UD if abut_name_UD else abut_name

    # 基準点
    ref_point_name = param_row["基準点_名称"]
    ref_point_2d = get_coord_data(coord_df, abut_name, ref_point_name)
    ref_point_z = param_row["全体_基準点z"] * 1000
    ref_point = Point3D(x=ref_point_2d.x, y=ref_point_2d.y, z=ref_point_z)

    # 1. Frame2Dの情報を取得
    point_u_name = param_row["軸方向_U名称"]
    point_d_name = param_row["軸方向_D名称"]
    points_for_vector = PointsForVector(
        point_u=get_coord_data(coord_df, abut_name, point_u_name),
        point_d=get_coord_data(coord_df, abut_name, point_d_name),
    )

    # 2. SeatInfoの情報を取得
    seat_info = SeatInfo(
        y_slope = MonoSlope(param_row["橋座_水切り傾き"]),
        UU_z = param_row["橋座_根本z_UU"]* 1000,
        UD_z = param_row["橋座_根本z_UD"]* 1000,
        DU_z = param_row["橋座_根本z_DU"]* 1000,
        DD_z = param_row["橋座_根本z_DD"]* 1000,
        U_x = param_row["橋座_Ux"],
        U_center_x = param_row["橋座_U中間x"],
        D_center_x = param_row["橋座_D中間x"],
        D_x = param_row["橋座_Dx"],
        y = param_row["橋座_y"],
    )

    # 3. BackwallInfoの情報を取得
    backwall_info = BackwallInfo(
        UUB_z = param_row["パラペット_根本上z_UU"]* 1000,
        UDB_z = param_row["パラペット_根本上z_UD"]* 1000,
        DUB_z = param_row["パラペット_根本上z_DU"]* 1000,
        DDB_z = param_row["パラペット_根本上z_DD"]* 1000,
        UUE_z = param_row["パラペット_外側上z_UU"]* 1000,
        UDE_z = param_row["パラペット_外側上z_UD"]* 1000,
        DUE_z = param_row["パラペット_外側上z_DU"]* 1000,
        DDE_z = param_row["パラペット_外側上z_DD"]* 1000,
        y = param_row["パラペット_y"],
    )

    # 4. WingInfoの情報を取得
    wing_info = WingInfo(
        U_z = param_row["ウィング_外側上z_U"]* 1000,
        D_z = param_row["ウィング_外側上z_D"]* 1000,
        U_x = param_row["ウィング_幅Ux"],
        D_x = param_row["ウィング_幅Dx"],
        Uab_y = param_row["ウィング_Uy上"],
        Dab_y = param_row["ウィング_Dy上"],
        Ubl_y = param_row["ウィング_Uy下"],
        Dbl_y = param_row["ウィング_Dy下"],
        Uab_height = param_row["ウィング_Uz上"],
        Dab_height = param_row["ウィング_Dz上"],
        Ubl_height = param_row["ウィング_Uz下"],
        Dbl_height = param_row["ウィング_Dz下"],
    )

    # 5. BarrierInfoの情報を取得
    barrier_info = BarrierInfo(
        U_overhang_Wing = True if param_row["壁高欄_Uタイプ"] == "はみだし" else False,
        D_overhang_Wing = True if param_row["壁高欄_Dタイプ"] == "はみだし" else False,
        BU_z = param_row["壁高欄_根本上z_U"]* 1000,
        BD_z = param_row["壁高欄_根本上z_D"]* 1000,
        CU_z = param_row["壁高欄_パラ境界上z_U"]* 1000,
        CD_z = param_row["壁高欄_パラ境界上z_D"]* 1000,
        EU_z = param_row["壁高欄_端上z_U"]* 1000,
        ED_z = param_row["壁高欄_端上z_D"]* 1000,
        BU_overhang_width = param_row["壁高欄_はみ出しU_根本x"],
        BD_overhang_width = param_row["壁高欄_はみ出しD_根本x"],
        EU_overhang_width = param_row["壁高欄_はみ出しU_外側x"],
        ED_overhang_width = param_row["壁高欄_はみ出しD_外側x"],
    )

    # 6. SlabSeatInfoの情報を取得
    slab_seat_info = SlabSeatInfo(
        y = param_row["踏掛版受_y"],
        B_ab_height = param_row["踏掛版受_根本上z"],
        E_ab_height = param_row["踏掛版受_外側上z"],
        height = param_row["踏掛版受_本体z"],
        straight_height = param_row["踏掛版受_端z"],
        U_x = param_row["踏掛版受_U側幅"],
        D_x = param_row["踏掛版受_D側幅"],
    )

    # 7. 基礎の情報を取得
    foundation_type = param_row["基礎_基礎形式"]
    foundation_offset = LocalOffset(
        x = 0,
        y = 0,
        z = (param_row["基礎_上z"] - param_row["全体_基準点z"]) * 1000,
    )
    foundation_z = param_row["基礎_上z"] * 1000
    # 5. FootingInfoの情報を取得
    if foundation_type == "杭基礎":
        footing_corner_names = ["フーチング左上", "フーチング左下", "フーチング右下", "フーチング右上"]
        footing_corner_points = get_four_corners(coord_df, abut_name, footing_corner_names)
        footing_info = FootingInfo(
            corner_points = footing_corner_points,
            reference_point = ref_point,
            reference_offset = foundation_offset,
            top_z=foundation_z,
            height = param_row["フーチング_z"],
        )
    else:
        footing_info = None

    # 6. PileFoundationの情報を取得
    if foundation_type == "杭基礎":
        pile_corner_names = ["場所打ち杭左上中心", "場所打ち杭左下中心", "場所打ち杭右下中心", "場所打ち杭右上中心"]
        pile_corner_points = get_four_corners(coord_df, abut_name, pile_corner_names)
        x_count = int(param_row["杭_x本数"])
        pile_foundation = PileFoundationInfo(
            corner_points = pile_corner_points,
            number_of_piles=param_row["杭_本数"],
            count_x = param_row["杭_x本数"],
            count_y = param_row["杭_y本数"],
            diameter = param_row["杭_直径"],
            depths_by_x = [param_row.get(f"杭_z_x{i}列目") * 1000 for i in range(1, x_count+1)],
        )
    else:
        pile_foundation = None

    # 7. CaissonFoundationの情報を取得
    if foundation_type == "深礎":
        # coord_dfの柱n中心を全部取る
        center_ref_point_names = [
            f"柱{i}中心" for i in range(1, 10)
            if f"柱{i}中心" in coord_df.columns
        ]
        centers = [
            p
            for name in center_ref_point_names
            for p in [get_coord_data(coord_df, abut_name, name)]
            if p is not None and not (abs(p.x) < 1e-9 and abs(p.y) < 1e-9)
        ]

        caisson_foundation = CaissonFoundationInfo(
            reference_point = ref_point,
            reference_offset = foundation_offset,
            top_z = foundation_z,
            diameter = param_row["深礎_直径"],
            depth = param_row["深礎_z"] * 1000,
            centers = centers,
        )
    
    else:
        caisson_foundation = None

    # 8. WaterTreatmentNotchの位置だけ
    notch_position = param_row["切欠_位置"]

    return (
        abut_name_merge,
        InputAbutInfo(
            points_for_vector = points_for_vector,
            ref_point = ref_point,
            bridge_type = param_row["全体_タイプ"],
            abut_type = param_row["全体_形式"],
            direction = "UP" if param_row["全体_向き"] == "始点" else "DOWN",
            seat = seat_info,
            backwall = backwall_info,
            wing = wing_info,
            barrier = barrier_info,
            slab_seat = slab_seat_info,
            footing = footing_info,
            piles = pile_foundation,
            caisson = caisson_foundation,
            notch_position = notch_position,
        )
    )

def get_common_abut_info(
    param_common_row: pd.Series,
) -> CommonAbutInfo:
    bridge_type = param_common_row["種類"]
    barrier_common_info = BarrierCommonInfo(
        slope = MonoSlope(value = param_common_row["壁高欄_水切り傾き"]),
        x = param_common_row["壁高欄_全体x"],
        face_x = param_common_row["壁高欄_壁x"],
        face_height = param_common_row["壁高欄_壁z"],
        haunch_x = param_common_row["壁高欄_地覆x"],
        haunch_height = param_common_row["壁高欄_地覆z"],
        base_height = param_common_row["壁高欄_立上げz"],
        edge_out_height = param_common_row["壁高欄_下外z"],
        edge_in_height = param_common_row["壁高欄_下内z"],
        edge_watertreatment_height = param_common_row["壁高欄_水切りはみだしz"],        
        edge_watertreatment_x = param_common_row["壁高欄_水切りはみだしx"],
        pavement_height = param_common_row["舗装厚"],
    )

    notch_info = WaterTreatmentNotchInfo(
        outer_x = param_common_row["切欠_外側x"],
        inner_x = param_common_row["切欠_内側x"],
        y = param_common_row["切欠_y"],
    )
    wall_info = WaterTreatmentWallInfo(
        width = param_common_row["水処理壁_w"],
        height = param_common_row["水処理壁_z"],
    )
    
    return (
        bridge_type,
        CommonAbutInfo(
            barrier_common_info = barrier_common_info,
            notch_info = notch_info,
            wall_info = wall_info,
        )
    )
    
def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR
    param_indiv_df = read_file_to_df(
        file_path = input_dir / "橋台諸元.xlsx",
        sheet_name="Individual",
        header = [0,1,2],
        fillna0=True,
    )
    coord_df = read_file_to_df(
        file_path = input_dir / "座標.xlsx",
        sheet_name="下部工座標",
        fillna0=True,
    )
    
    indiv_infos = dict()
    for _, param_row in param_indiv_df.iterrows():
        abut_name, indiv_info = get_indiv_abut_info(param_row, coord_df)
        indiv_infos[abut_name] = indiv_info

    save_json_and_pickle(
        data = indiv_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.ABUT}_{Filenames.INDIV}",
    )

    param_common_df = read_file_to_df(
        file_path = input_dir / "橋台諸元.xlsx",
        sheet_name="Common",
        header = [0,1,2],
        fillna0=True,
    )

    common_infos = dict()
    for _, param_common_row in param_common_df.iterrows():
        bridge_type, common_info = get_common_abut_info(param_common_row)
        common_infos[bridge_type] = common_info

    save_json_and_pickle(
        data = common_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.ABUT}_{Filenames.COMMON}",
    )

if __name__ == "__main__":
    main("initial")


