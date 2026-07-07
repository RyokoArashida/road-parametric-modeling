"""
このファイルではブロック積みしか実装していない。
In this file, only block walls are implemented.
"""
import re

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.wall_schemas import BlockInfo, RefPointInfo, WallInfo
from my_project.config.util_schemas import (
    MonoSlope,
)
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_block_info(size_info_row):
    return BlockInfo(
        num = size_info_row["全体_番号"],
        front_slope = MonoSlope(size_info_row["全体_表勾配"]),
        back_slope = MonoSlope(size_info_row["全体_裏勾配"]),
        embed_depth = size_info_row["全体_根入れ"],
        foundation_front_height = size_info_row["基礎工_表高さ"],
        foundation_back_height = size_info_row["基礎工_裏高さ"],
        foundation_front_offset = size_info_row["基礎工_控え"],
        block_width = size_info_row["ブロック_控え"],
        backfill_concrete_width = size_info_row["裏込めコン_控え"],
        backfill_stone_top_width = size_info_row["裏込め砕石_天端控え"]
    )


def parse_point_num_list(value):
    point_nums = str(value).split(",") if not pd.isna(value) else []
    return [int(float(num)) for num in point_nums]


def get_wall_info(indiv_info_row, size_info):
    # 値が入っている上点高さ_図面の最大番号を取得する
    ref_point_num = max(
        int(re.search(r"\d+$", col).group()) for col in indiv_info_row.index if col.startswith("上点高さ_図面") if not pd.isna(indiv_info_row[col])
    )
    reference_points = []
    for i in range(1, ref_point_num + 1):
        top_z = indiv_info_row[f"上点高さ_図面{i}"] * 1000  # m -> mm
        bottom_z = indiv_info_row[f"下点高さ_図面{i}"] * 1000  # m -> mm
        top_num = indiv_info_row[f"上点点番号_図面{i}"]
        bottom_num = indiv_info_row[f"下点点番号_図面{i}"]
        ref_point_info = RefPointInfo(
            top_z=top_z,
            bottom_z=bottom_z,
            top_num=top_num,
            bottom_num=bottom_num
        )
        reference_points.append(ref_point_info)
    top_gap_point_num = parse_point_num_list(indiv_info_row["過剰点_上"])
    bottom_gap_point_num = parse_point_num_list(indiv_info_row["過剰点_下"])
    berm_gap_point_num = parse_point_num_list(indiv_info_row["過剰点_小段"])
    return WallInfo(
        location=indiv_info_row["全体_大名称"],
        name=indiv_info_row["全体_小名称"],
        wall_type=indiv_info_row["全体_種別"],
        block_info=size_info,
        reference_points=reference_points,
        top_gap_point_num=top_gap_point_num,
        bottom_gap_point_num=bottom_gap_point_num,
        berm_gap_point_num=berm_gap_point_num
    )



def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    excel_path = input_dir / "擁壁諸元.xlsx"
    indiv_infos_df = read_file_to_df(
        file_path = excel_path,
        sheet_name = "擁壁情報",
        header = [0,1]
    )
    size_infos_df = read_file_to_df(
        file_path = excel_path,
        sheet_name = "擁壁寸法",
        header = [0,1]
    )
    size_infos = {}
    for _, row in size_infos_df.iterrows():
        if row["全体_種別"] == "ブロック積み":
            size_infos[(row["全体_種別"], row["全体_番号"])] = get_block_info(row)
        else:
            raise ValueError(f"Unknown wall type: {row['全体_種別']}")
    wall_infos = []
    for _, row in indiv_infos_df.iterrows():
        wall_type = row["全体_種別"]
        wall_num = row["全体_番号"]
        size_info = size_infos.get((wall_type, wall_num))
        wall_info = get_wall_info(row, size_info)
        wall_infos.append(wall_info)


    save_json_and_pickle(
        data = wall_infos,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.WALL}",
    )

if __name__ == "__main__":
    main("initial")
