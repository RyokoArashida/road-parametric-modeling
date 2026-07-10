import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    get_input_Rhino_dir,
    get_output_dir,
)
from my_project.config.schemas.embankment_schemas import (
    CrossSectionInfo,
    EdgePoints,
    LocalTopBottomPointInfo,
)
from my_project.config.util_schemas import Point3D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def clean_optional_name(value):
    if pd.isna(value):
        return None
    return str(value)


def get_info_UD(
    embankment_df: pd.DataFrame,
    wall_df: pd.DataFrame,
    tier_num: int,
) -> EdgePoints:
    points = []
    for tier in range(1, int(tier_num) + 1):
        top_point = None
        bottom_point = None
        embankment_tier_df = embankment_df[embankment_df["段番号"] == tier]
        for _, row in embankment_tier_df.iterrows():
            point = Point3D(
                x=row["X"],
                y=row["Y"],
                z=row["Z"],
            )
            if row["点種"] == "法肩":
                top_point = point
            elif row["点種"] == "法尻":
                bottom_point = point
        if top_point is None or bottom_point is None:
            raise ValueError(f"Missing embankment top or bottom point: tier={tier}")
        points.append(LocalTopBottomPointInfo(top=top_point, bottom=bottom_point))

    if len(wall_df) == 0:
        return EdgePoints(points=points)

    wall_points = []
    wall_positions = []
    is_wall_only = []
    wall_names = []
    wall_tier_num = int(max(wall_df["擁壁番号"].unique()))
    for tier in range(1, wall_tier_num + 1):
        top_point = None
        bottom_point = None
        wall_tier_df = wall_df[wall_df["擁壁番号"] == tier]
        wall_positions.append(int(wall_tier_df["段番号"].iloc[0]))
        is_wall_only.append(wall_tier_df["擁壁段区分"].iloc[0] == "擁壁だけの段")
        wall_names.append(clean_optional_name(wall_tier_df["擁壁名前"].iloc[0]))
        for _, row in wall_tier_df.iterrows():
            point = Point3D(
                x=row["X"],
                y=row["Y"],
                z=row["Z"],
            )
            if row["点種"] == "外側上端":
                top_point = point
            elif row["点種"] == "外側下端（地表面高）":
                bottom_point = point
        if top_point is None or bottom_point is None:
            raise ValueError(f"Missing wall top or bottom point: tier={tier}")
        wall_points.append(LocalTopBottomPointInfo(top=top_point, bottom=bottom_point))

    return EdgePoints(
        points=points,
        wall_points=wall_points,
        wall_positions=wall_positions,
        is_wall_only=is_wall_only,
        wall_names=wall_names,
    )


def get_indiv_local_embankment_info(df: pd.DataFrame) -> tuple[str, list[CrossSectionInfo]]:
    name = df["共通名前"].iloc[0]
    df["STA"] = df.apply(lambda row: get_STA_from_STA_info(row["STA大"], row["STA小"]), axis=1)
    df = df.sort_values(by="STA")
    infos = []
    for STA, group_df in df.groupby("STA"):
        U_group = group_df[group_df["線側"] == "上り線"]
        D_group = group_df[group_df["線側"] == "下り線"]
        U_tier_num = max(U_group["段番号"].unique())
        D_tier_num = max(D_group["段番号"].unique())
        U_embankment_df = U_group[U_group["種別"] == "盛土"]
        D_embankment_df = D_group[D_group["種別"] == "盛土"]
        U_wall_df = U_group[U_group["種別"] == "擁壁"]
        D_wall_df = D_group[D_group["種別"] == "擁壁"]
        infos.append(
            CrossSectionInfo(
                STA=STA,
                U_points=get_info_UD(U_embankment_df, U_wall_df, U_tier_num),
                D_points=get_info_UD(D_embankment_df, D_wall_df, D_tier_num),
            )
        )
    return name, infos


def main(initial_or_final: str) -> None:
    input_rhino_dir = get_input_Rhino_dir(initial_or_final)
    output_dir = get_output_dir(initial_or_final)
    embankment_files = [
        f for f in input_rhino_dir.glob("*.csv")
        if Filenames.EMBANKMENT in f.name and "abut" not in f.name.lower()
    ]

    local_embankment_points_dict = {}
    for file_path in embankment_files:
        name, indiv_info = get_indiv_local_embankment_info(read_file_to_df(file_path=file_path))
        local_embankment_points_dict[name] = indiv_info

    save_json_and_pickle(
        data=local_embankment_points_dict,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.LOCAL}_{Filenames.EMBANKMENT}_{Filenames.POINTS}",
    )


if __name__ == "__main__":
    main(initial_or_final="initial")
