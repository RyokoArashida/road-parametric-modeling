

from typing import Optional, Union

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.config.util_schemas import (
    MonoSlope,
    Point2D,
    Point3D,
)
from my_project.utils.geometry.vectors import get_frame_2D
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_Point3D_from_row(df_row: pd.Series, point_key: str) -> Optional[Union[Point3D, Point2D]]:
    if pd.isna(df_row[f"{point_key}_x"]) or pd.isna(df_row[f"{point_key}_y"]) :
        return None
    if df_row[f"{point_key}_z"] == 0 or pd.isna(df_row[f"{point_key}_z"]):
        return Point2D(
            x = df_row[f"{point_key}_y"] * 1000, # xとyは逆
            y = df_row[f"{point_key}_x"] * 1000,
        )
    return Point3D(
        x = df_row[f"{point_key}_y"] * 1000, # xとyは逆
        y = df_row[f"{point_key}_x"] * 1000,
        z = df_row[f"{point_key}_z"] * 1000,
    )

def get_indiv_superstructure_coord_info(
    df_row: pd.Series,
    point_keys: list[str],
) -> CoordInfo:
    girder_name = df_row["全体_横桁"]
    point_dict = dict()
    for point_key in point_keys:
        point_dict[point_key] = get_Point3D_from_row(df_row, point_key)
    L2_cols = ["UL2", "DL2", "CL2", "BL2"]
    R2_cols = ["UR2", "DR2", "CR2", "BR2"]
    for L2_col in L2_cols:
        if L2_col in point_dict and point_dict[L2_col] is not None and isinstance(point_dict[L2_col], Point3D):
            U_point = point_dict[L2_col]
            break
    for R2_col in R2_cols:
        if R2_col in point_dict and point_dict[R2_col] is not None and isinstance(point_dict[R2_col], Point3D):
            D_point = point_dict[R2_col]
            break
    UDframe2D = get_frame_2D(U_point, D_point, y_direction="UP")
    UDslope = MonoSlope(
        value = (U_point.z - D_point.z) / ((U_point.x - D_point.x)**2 + (U_point.y - D_point.y)**2)**0.5)
    return CoordInfo(
        name = girder_name,
        UDframe2D = UDframe2D,
        UDslope = UDslope,
        Points = point_dict,
    )
    
def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        this_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        this_dir = FINAL_OUTPUT_DIR
    coord_df = read_file_to_df(
        file_path = this_dir / f"{Filenames.SUPERSTRUCTURE}_{Filenames.COORDS}.xlsx",
    )

    colnames = coord_df.columns
    coord_colnames = [colname for colname in colnames if colname.endswith("_x")]
    coord_colnames = [colname[:-2] for colname in coord_colnames]

    bridge_df_dict = {
        name: group
        for name, group in coord_df.groupby("全体_橋梁", sort=False)
    }

    all_coord_info_dict = dict()
    for key, df in bridge_df_dict.items():
        coord_infos = []
        for _, row in df.iterrows():
            coord_info = get_indiv_superstructure_coord_info(row, coord_colnames)
            coord_infos.append(coord_info)
        all_coord_info_dict[key] = coord_infos
    
    save_json_and_pickle(
        data = all_coord_info_dict,
        folder_path = this_dir,
        name = f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}",
    )

if __name__ == "__main__":
    main("initial")


