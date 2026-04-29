
import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.barrier_schemas import (
    BarrierCommonInfo,
    BarrierInfo,
    CenterBarrierInfo,
    CenterBarrierNoseInfo,
    LR_point,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.config.util_schemas import MonoSlope, Point3D
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_indiv_barrier_info(
    bridge_name: str,
    num: str,
    barrier_df_row: pd.Series,
    bridge_df_row: pd.Series,
    L_top_point_dict: dict[str, Point3D],
    R_top_point_dict: dict[str, Point3D],
) -> BarrierInfo:
    common_info = BarrierCommonInfo(
        slope = MonoSlope(barrier_df_row["勾配"]),
        x = barrier_df_row["壁高欄幅"],
        face_x = barrier_df_row["壁幅"],
        face_height = barrier_df_row["壁高さ"],
        haunch_x = barrier_df_row["地覆幅"],
        haunch_height = barrier_df_row["地覆高さ"],
        base_height = barrier_df_row["立上高さ"],
        edge_in_height = bridge_df_row["端高さ"], # アバットとはちょっと違う
        edge_out_height = 0, #使わない
        edge_watertreatment_height= barrier_df_row["水切り高さ"],
        edge_watertreatment_x = barrier_df_row["水切り幅"],
        pavement_height = bridge_df_row["舗装高さ"]
    )
    slab_edge_points = []
    for key, L_top_point in L_top_point_dict.items():
        if key not in R_top_point_dict:
            raise ValueError(f"key {key} is in L_top_point_dict but not in R_top_point_dict")
        R_top_point = R_top_point_dict[key]
        slab_edge_points.append(
            LR_point(
                name = key,
                Lpoint = L_top_point,
                Rpoint = R_top_point,
            )
        )
    barrier_info = BarrierInfo(
        bridge_name = bridge_name,
        num = num,
        common_info = common_info,
        slab_edge_points = slab_edge_points,
    )
    return barrier_info, common_info

def get_indiv_center_barrier_info(
    bridge_name: str,
    num: str,
    barrier_common_info: BarrierCommonInfo,
    center_barrier_df_row: pd.Series,
    coord_infos: list[CoordInfo],
) -> CenterBarrierInfo:
    nose_common_info = CenterBarrierNoseInfo(
        length = center_barrier_df_row["ノーズ延長"],
        height = center_barrier_df_row["マウントアップ高さ"],
        edge_cut_width = center_barrier_df_row["切欠幅"],
        start_cross_girder_key = center_barrier_df_row["ノーズ開始横桁"],
        start_offset = center_barrier_df_row["ノーズ開始横桁距離"],
    )
    start_cross_girder_key = center_barrier_df_row["開始"]
    end_cross_girder_key = center_barrier_df_row["ノーズ開始横桁"]
    L_point_name = center_barrier_df_row["中央左"]
    R_point_name = center_barrier_df_row["中央右"]
    start_idx = next(i for i, c in enumerate(coord_infos) if c.name == start_cross_girder_key)
    end_idx = next(i for i, c in enumerate(coord_infos) if c.name == end_cross_girder_key)
    extend_end_idx = min(end_idx + 10, len(coord_infos)-1)
    LR2_points = []
    for i in range(start_idx, extend_end_idx+1):
        coord_info_i = coord_infos[i]
        name = coord_info_i.name
        L2_point = coord_info_i.Points.get(L_point_name)
        R2_point = coord_info_i.Points.get(R_point_name)
        if L2_point is None or R2_point is None:
            if "GE" in name:
                continue # GEは点を用意しないので、L2やR2の点がなくてもスキップする
            print("最後の点:", name)
            break # 点がなくなるところまで。
        LR2_points.append(
            LR_point(
                name = name,
                Lpoint = L2_point,
                Rpoint = R2_point,
            )
        )
    center_barrier_info = CenterBarrierInfo(
        bridge_name = bridge_name,
        num = num,
        barrier_common_info = barrier_common_info,
        nose_common_info = nose_common_info,
        LR2_points = LR2_points,
    )
    return center_barrier_info

def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    common_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "床版共通"
    )
    barrier_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "壁高欄共通"
    )
    center_barrier_df = read_file_to_df(
        file_path = input_dir / "床版諸元.xlsx",
        sheet_name = "中央壁高欄"
    )
    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )
    all_L_top_point_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.UP}_{Filenames.TOP}_{Filenames.POINTS}.pickle",
    )
    all_R_top_point_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.WORLD}_{Filenames.SLAB}_{Filenames.DOWN}_{Filenames.TOP}_{Filenames.POINTS}.pickle",
    )


    all_barrier_infos = list()
    all_center_barrier_infos= list()
    for _, row in common_df.iterrows():
        name = row["橋梁"]
        num = str(row["番号"])
        unique_name = f"{name}_{num}"
        barrier_df_row = barrier_df[barrier_df["橋梁"] == row["壁高欄タイプ"]].iloc[0]
        barrier_info, barrier_common_info = get_indiv_barrier_info(
            bridge_name = name,
            num = num,
            barrier_df_row = barrier_df_row,
            bridge_df_row = row,
            L_top_point_dict = all_L_top_point_dict[unique_name],
            R_top_point_dict = all_R_top_point_dict[unique_name],
        )
        all_barrier_infos.append(barrier_info)

        center_barrier_df_row = center_barrier_df[(center_barrier_df["橋梁"] == name) & (center_barrier_df["番号"].astype(str) == num)]
        if len(center_barrier_df_row) == 0:
            continue
        center_barrier_info = get_indiv_center_barrier_info(
            bridge_name = name,
            num = num,
            barrier_common_info = barrier_common_info,
            center_barrier_df_row = center_barrier_df_row.iloc[0],
            coord_infos = coord_dict[name],
        )
        all_center_barrier_infos.append(center_barrier_info)

    save_json_and_pickle(
        data = all_barrier_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.SLAB}_{Filenames.BARRIER}",
    )
    save_json_and_pickle(
        data = all_center_barrier_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.SLAB}_{Filenames.BARRIER}_{Filenames.CENTER}",
    )

if __name__ == "__main__":
    main("initial")


