

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.util_schemas import (
    LocalOffset,
    Point2D,
)
from my_project.utils.geometry.points import offset_point_in_frame
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.io import read_file_to_df, save_df_to_file


def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)
    trans_df = read_file_to_df(
        file_path = input_dir / "上部工座標.xlsx",
        sheet_name="変換表",
    )

    world_df_list = []
    for _, trans_row in trans_df.iterrows():
        key = trans_row["橋梁"]
        start_point = Point2D(x=trans_row["始点X"], y=trans_row["始点Y"])
        end_point = Point2D(x=trans_row["終点X"], y=trans_row["終点Y"])
        ref_point = LocalOffset(x=start_point.x, y=start_point.y, z=0)
        frame_2D = get_frame_2D(start_point, end_point, "DOWN")

        coord_df = read_file_to_df(
            file_path = input_dir / "上部工座標.xlsx",
            sheet_name=key,
            header = [0,1],
            flatten_columns=True,
        )
        
        world_df = coord_df.copy()
        # 全体_横桁列に値が入っているものだけ残す
        world_df = world_df[~world_df["全体_横桁"].isna()].reset_index(drop=True)

        # x列の対応だけ先に拾う
        xyz_col_sets = []
        for col in world_df.columns:
            col_tuple = col.split("_")
            if not col_tuple[-1] == "x":
                continue
            x_col = col
            prefix = "_".join(col_tuple[:-1])
            y_col = prefix + "_y"
            z_col = prefix + "_z"
            xyz_col_sets.append((x_col, y_col, z_col))

        for idx in world_df.index:
            if pd.isna(world_df.at[idx, "全体_横桁"]):
                continue
            for x_col, y_col, z_col in xyz_col_sets:
                if pd.isna(world_df.at[idx, x_col]) or pd.isna(world_df.at[idx, y_col]):
                    continue
                flag2D = pd.isna(world_df.at[idx, z_col])
                if flag2D:
                    world_df.at[idx, z_col] = 0
                world_point = offset_point_in_frame(
                    point=ref_point,
                    local_offset=LocalOffset(
                        x=world_df.at[idx, x_col],
                        y=world_df.at[idx, y_col],
                        z=world_df.at[idx, z_col],
                    ),
                    frame_2D=frame_2D,
                )
                world_df.at[idx, x_col] = world_point.x
                world_df.at[idx, y_col] = world_point.y
                if flag2D:
                    world_df.at[idx, z_col] = 0
                else:
                    world_df.at[idx, z_col] = world_point.z
        
        world_df["全体_橋梁"] = key
        world_df_list.append(world_df)
    
    world_df = pd.concat(world_df_list, ignore_index=True)

    file_name = f"{Filenames.SUPERSTRUCTURE}_{Filenames.COORDS}.xlsx"
    save_df_to_file(world_df, output_dir / file_name, index = False)


if __name__ == "__main__":
    main("initial")



