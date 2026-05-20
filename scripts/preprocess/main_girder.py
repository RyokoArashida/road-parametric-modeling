from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.main_girder_schemas import (
    GirderBlockInfo,
    HeightChangeInfo,
    MainGirderInfo,
    WidthChangeInfo,
)
from my_project.config.schemas.slab_schemas import (
    SlabInfo,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle


def get_Point3D_from_row(df_row: pd.Series, point_key: str) -> Optional[Point3D]:
    if pd.isna(df_row[f"{point_key}_x"]) or pd.isna(df_row[f"{point_key}_y"]) or pd.isna(df_row[f"{point_key}_z"]):
        return None
    return Point3D(
        x = df_row[f"{point_key}_y"], # xとyは逆
        y = df_row[f"{point_key}_x"],
        z = df_row[f"{point_key}_z"],
    )

def get_original_CG_names(
    coord_info_list_for_bridge: list[CoordInfo],
    girder_names: str,
) -> dict[str, list[str]]:
    CG_names_dict = dict()
    for girder_name in girder_names:
        CG_names_dict[girder_name] = []
    for coord_info in coord_info_list_for_bridge:
        CG= coord_info.name
        points = coord_info.Points
        for key, _ in points.items():
            for girder_name in girder_names:
                if key == girder_name and not pd.isna(points[key]):
                    CG_names_dict[girder_name].append(CG)
    true_CG_names_dict = dict()
    for girder_name, CG_names in CG_names_dict.items():
        ture_CG_names = []
        for i, CG_name in enumerate(CG_names):
            if "GE" in CG_name and i != 0 and i != len(CG_names)-1:
                continue
            ture_CG_names.append(CG_name)
        true_CG_names_dict[girder_name] = ture_CG_names
    return true_CG_names_dict

def get_indiv_girder_info(
    bridge_name: str,
    girder_name: str,
    df_row: pd.Series,
    block_df_for_MG: pd.DataFrame,
    width_change_df_for_MG: pd.DataFrame,
    height_change_df_for_MG: pd.DataFrame,
    original_CG_names: list[str],
) -> SlabInfo:
    girder_type = df_row["形式"]
    basic_height = df_row["基本桁高さ"]
    bottom_flange_width = df_row["下フランジy"]
    web_offset = df_row["中心からウェブ端x"]

    block_infos = []
    for i, row in block_df_for_MG.iterrows():
        block_infos.append(GirderBlockInfo(
            CG = row["距離基準"],
            CG_offset = row["相対距離"],
            top_flange_thickness = row["上フランジ厚"],
            bottom_flange_thickness = row["下フランジ厚"],
            web_thickness = row["腹板厚"],
        ))
    width_change_infos = []
    for i, row in width_change_df_for_MG.iterrows():
        if "GE1" in row["横桁"]:
            change_type = "start"
        elif "GE2" in row["横桁"]:
            change_type = "end"
        else:
            change_type = "middle"
        width_change_infos.append(WidthChangeInfo(
            CG = row["横桁"],
            y = row["中央y"],
            straight_x = row["中央x"],
            slope_x = row["擦付x"],
            change_type = change_type,
        ))

    height_change_infos = []
    for _, row in height_change_df_for_MG.iterrows():
        height_change_infos.append(HeightChangeInfo(
            start_CG = row["変化開始横桁"],
            start_offset = row["変化開始横桁から距離"],
            straight_start_CG = row["水平開始横桁"],
            straight_start_offset = row["水平開始横桁から距離"],
            straight_end_CG = row["水平終了横桁"],
            straight_end_offset = row["水平終了横桁から距離"],
            end_CG = row["変化終了横桁"],
            end_offset = row["変化終了横桁から距離"],
            height = row["変化高さ"],
        ))
    

    return MainGirderInfo(
        bridge_name = bridge_name,
        MG_name = girder_name,
        MG_type = girder_type,
        basic_height = basic_height,
        bottom_flange_width = bottom_flange_width,
        web_offset = web_offset,
        block_infos = block_infos,
        width_change_infos = width_change_infos,
        height_change_infos = height_change_infos,
        original_CG_names= original_CG_names,
    )


def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    common_df = read_file_to_df(
        file_path = input_dir / "主桁諸元.xlsx",
        sheet_name = "主桁諸元"
    )
    block_df = read_file_to_df(
        file_path = input_dir / "主桁諸元.xlsx",
        sheet_name = "接合部諸元"
    )
    width_change_df = read_file_to_df(
        file_path = input_dir / "主桁諸元.xlsx",
        sheet_name = "幅変化部諸元"
    )
    height_change_df = read_file_to_df(
        file_path = input_dir / "主桁諸元.xlsx",
        sheet_name = "桁高さ追加点"
    )
    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )

    bridge_names = coord_dict.keys()
    original_CG_names_dict = dict()
    for bridge_name in bridge_names:
        original_girder_names = common_df[common_df["橋梁"] == bridge_name]["主桁"].tolist()
        original_CG_names = get_original_CG_names(
            coord_info_list_for_bridge = coord_dict[bridge_name],
            girder_names = original_girder_names,
        )
        original_CG_names_dict[bridge_name] = original_CG_names
    
    all_MG_infos = []
    for _, common_row in common_df.iterrows():
        bridge_name = common_row["橋梁"]
        girder_name = common_row["主桁"]
        block_df_for_MG = block_df[(block_df["橋梁"] == bridge_name) & (block_df["主桁"] == girder_name)]
        width_change_df_for_MG = width_change_df[(width_change_df["橋梁"] == bridge_name) & (width_change_df["主桁"] == girder_name)]
        height_change_df_for_MG = height_change_df[(height_change_df["橋梁"] == bridge_name) & (height_change_df["主桁"] == girder_name)]
        original_CG_names = original_CG_names_dict[bridge_name][girder_name]
        print(f"Processing bridge {bridge_name}, girder {girder_name} with original CG names: {original_CG_names}")
        girder_info = get_indiv_girder_info(
            bridge_name = bridge_name,
            girder_name = girder_name,
            df_row = common_row,
            block_df_for_MG = block_df_for_MG,
            width_change_df_for_MG = width_change_df_for_MG,
            height_change_df_for_MG = height_change_df_for_MG,
            original_CG_names = original_CG_names,
        )
        all_MG_infos.append(girder_info)
        
    save_json_and_pickle(
        data = all_MG_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.MG}",
    )

if __name__ == "__main__":
    main("initial")


