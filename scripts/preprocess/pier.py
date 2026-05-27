

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.pier_schemas import (
    CaissonFoundationInfo,
    ColumnInfo,
    CommonPierInfo,
    FootingInfo,
    InputPierInfo,
    MaxPierTopX,
    PierTopHeightProfile,
    PierTopInfo,
    PierTopSurfInfo,
    PierTopXProfile,
    PileFoundationInfo,
    PointsForVector,
    WaterTreatmentNotchInfo,
    WaterTreatmentWallInfo,
)
from my_project.config.util_schemas import (
    CrownSlope,
    LocalOffset,
    MonoSlope,
    Point3D,
)
from my_project.utils.io import read_file_to_df, save_json_and_pickle
from my_project.utils.preprocess import get_coord_data, get_four_corners


def get_indiv_pier_info(
    param_row: pd.Series,
    coord_df: pd.DataFrame,
) -> InputPierInfo:
    pier_name = param_row["全体_橋脚名"]
    pier_name_UD = None if pd.isna(param_row["全体_上下"]) else param_row["全体_上下"]
    pier_name_merge = pier_name + pier_name_UD if pier_name_UD else pier_name
    pier_type = param_row["全体_タイプ"]

    # 基準点
    ref_point_name = param_row["基準点_名称"]
    ref_point_2d = get_coord_data(coord_df, pier_name, ref_point_name)
    ref_point_z = param_row["基準点_z"] * 1000
    ref_point = Point3D(x=ref_point_2d.x, y=ref_point_2d.y, z=ref_point_z)

    # 1. PierFrame2Dの情報を取得
    point_u_name = param_row["軸方向_U名称"]
    point_d_name = param_row["軸方向_D名称"]
    points_for_vector = PointsForVector(
        point_u=get_coord_data(coord_df, pier_name, point_u_name),
        point_d=get_coord_data(coord_df, pier_name, point_d_name),
    )

    # 2. PierTopSurfInfoの情報を取得
    pier_top_reference_offset = LocalOffset(
        x = -1 * param_row["全体_基準点からUx"],
        y = 0,
        z = 0
    )
    pier_top_surf_info = PierTopSurfInfo(
        reference_point = ref_point,
        reference_offset = pier_top_reference_offset,
        width_y = param_row["橋座_y"],
        u2d_slope = MonoSlope(param_row["橋座_UD傾き"]),
        crown_slope = CrownSlope(param_row["橋座_水切り傾き"]),
    )

    # 3. ColumnInfoの情報を取得
    column_info = ColumnInfo(
        outer_x = param_row["柱_外側x"],
        inner_x = param_row["柱_内側x"],
        outer_y = param_row["柱_外側y"],
        inner_y = param_row["橋座_y"],
    )

    # 4. PierTopInfoの情報を取得
    pier_top_height_profile = PierTopHeightProfile(
        top_U_z = param_row["梁_U上z"] if param_row["梁_U上z"]>0 else param_row["梁_柱上z"],
        top_D_z = param_row["梁_D上z"] if param_row["梁_D上z"]>0 else param_row["梁_柱上z"],
        top_z = param_row["梁_柱上z"],
        mid_top_z = param_row["梁_中間上z"],
        bottom_z = param_row["梁_下z"],
    )
    pier_top_u_side_x_profile = PierTopXProfile(
        pier_top_x_type = param_row["梁_U端xタイプ"],
        max = param_row["梁_U端x最大値有無"],
        x = param_row["梁_U端x"],
    )
    pier_top_d_side_x_profile = PierTopXProfile(
        pier_top_x_type = param_row["梁_D端xタイプ"],
        max = param_row["梁_D端x最大値有無"],
        x = param_row["梁_D端x"],
    )
    between_columns_x_profiles = []
    for i in range(1, 10):
        x = param_row.get(f"梁_スパンx_{i}")
        if (pd.isna(x) or x == 0):
            break
        between_columns_x_profiles.append(
            PierTopXProfile(
                pier_top_x_type = param_row.get(f"梁_スパンxタイプ_{i}"),
                x = x,
                max = True
            )
        )
    pier_top_info = PierTopInfo(
        heights = pier_top_height_profile,
        u_side_x = pier_top_u_side_x_profile,
        d_side_x = pier_top_d_side_x_profile,
        between_columns_x = between_columns_x_profiles,
    )

    foundation_type = param_row["基礎_基礎形式"]
    foundation_offset = LocalOffset(
        x = 0,
        y = 0,
        z = -1 * param_row["基礎_基準点からz"],
    )
    # 5. FootingInfoの情報を取得
    if foundation_type == "杭基礎":
        footing_corner_names = ["フーチング左上", "フーチング左下", "フーチング右下", "フーチング右上"]
        footing_corner_points = get_four_corners(coord_df, pier_name, footing_corner_names)
        footing_info = FootingInfo(
            corner_points = footing_corner_points,
            reference_point = ref_point,
            reference_offset = foundation_offset,
            height = param_row["フーチング_z"],
        )
    else:
        footing_info = None

    # 6. PileFoundationの情報を取得
    if foundation_type == "杭基礎":
        pile_corner_names = ["場所打ち杭左上中心", "場所打ち杭左下中心", "場所打ち杭右下中心", "場所打ち杭右上中心"]
        pile_corner_points = get_four_corners(coord_df, pier_name, pile_corner_names)
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
            for p in [get_coord_data(coord_df, pier_name, name)]
            if p is not None and not (abs(p.x) < 1e-9 and abs(p.y) < 1e-9)
        ]

        caisson_foundation = CaissonFoundationInfo(
            reference_point = ref_point,
            reference_offset = foundation_offset,
            diameter = param_row["深礎_直径"],
            depth = param_row["深礎_z"] * 1000,
            centers = centers,
        )
    
    else:
        caisson_foundation = None

    # 8. WaterTreatmentNotchの位置だけ
    notch_position = param_row["切欠_位置"]

    return (
        pier_name_merge,
        InputPierInfo(
            points_for_vector = points_for_vector,
            type = pier_type,
            piertop_surf = pier_top_surf_info,
            column = column_info,
            piertop = pier_top_info,
            footing = footing_info,
            piles = pile_foundation,
            caisson = caisson_foundation,
            notch_position = notch_position,
        )
    )

def get_common_pier_info(
    param_common_row: pd.Series,
) -> CommonPierInfo:
    bridge_type = param_common_row["種類"]
    notch_info = WaterTreatmentNotchInfo(
        outer_x = param_common_row["切欠_外側x"],
        inner_x = param_common_row["切欠_内側x"],
        y = param_common_row["切欠_y"],
    )
    wall_info = WaterTreatmentWallInfo(
        width = param_common_row["水処理壁_w"],
        height = param_common_row["水処理壁_z"],
    )
    max_piertop_x = MaxPierTopX(
        max_slope_x = param_common_row["梁_直線部最大x"],
        max_curve_x = param_common_row["梁_曲線部最大x"],
    )
    return (
        bridge_type,
        CommonPierInfo(
            notch_info = notch_info,
            wall_info = wall_info,
            max_piertop_x = max_piertop_x,
        )
    )
    
def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)
    param_indiv_df = read_file_to_df(
        file_path = input_dir / "橋脚諸元.xlsx",
        sheet_name="Individual",
        header = [0,1,2],
        fillna0=True,
    )
    coord_df = read_file_to_df(
        file_path = input_dir / "下部工座標.xlsx",
        sheet_name="下部工座標",
        fillna0=True,
    )
    
    indiv_infos = dict()
    for _, param_row in param_indiv_df.iterrows():
        pier_name, indiv_info = get_indiv_pier_info(param_row, coord_df)
        indiv_infos[pier_name] = indiv_info

    save_json_and_pickle(
        data = indiv_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}",
    )

    param_common_df = read_file_to_df(
        file_path = input_dir / "橋脚諸元.xlsx",
        sheet_name="Common",
        header = [0,1,2],
        fillna0=True,
    )

    common_infos = dict()
    for _, param_common_row in param_common_df.iterrows():
        bridge_type, common_info = get_common_pier_info(param_common_row)
        common_infos[bridge_type] = common_info

    save_json_and_pickle(
        data = common_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.COMMON}",
    )

if __name__ == "__main__":
    main("initial")


