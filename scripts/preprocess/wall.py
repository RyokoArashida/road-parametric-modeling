"""
このファイルではブロック積みしか実装していない。
In this file, only block walls are implemented.
"""
from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.wall_schemas import (
    BlockInfo,
    RefPointInfo,
    WallInfo,
)
from my_project.config.util_schemas import Point2D
from my_project.utils.io import read_file_to_df, save_json_and_pickle



def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

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
    print(indiv_infos_df.head())
    print(size_infos_df.head())
    # wall_infos = []
    # for _, row in indiv_infos_df.iterrows():
    #     wall_type = row["全体_形状"]
    #     wall_info = get_wall_info(row, size_infos_df)


    # save_json_and_pickle(
    #     data = road_center_info_dict,
    #     folder_path = output_dir,
    #     name = f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}",
    # )


if __name__ == "__main__":
    main("initial")
