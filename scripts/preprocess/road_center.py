

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import (
    FINAL_INPUT_DIR,
    FINAL_OUTPUT_DIR,
    INITIAL_INPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.road_center_schemas import (
    RoadCenterInfo,
    ZInfo,
    typeInfo,
)
from my_project.config.util_schemas import Point2D
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_STA_from_STA_info(big: float, small: float) -> float:
    return (big * 100 + small) * 1000 # staは100m + m単位


def get_road_center_info(plan_road_center_df: pd.DataFrame, z_road_center_df: pd.DataFrame) -> RoadCenterInfo:
    STAs = []
    Coord_infos = []
    type_infos = []
    z_infos = []
    for _, row in plan_road_center_df.iterrows():
        STA = get_STA_from_STA_info(row["測点大"], row["測点小"])
        Coord_info = Point2D(
            x = row["X座標"]*1000,
            y = row["Y座標"]*1000,
        )
        if row["形式"] == "直線":
            row["形式"] = "line"
        elif row["形式"] == "曲線":
            row["形式"] = "arc"
        elif row["形式"] == "クロソイド":
            row["形式"] = "clothoid"
        direction = None
        if row["向き"] == "左":
            direction = "left"
        elif row["向き"] == "右":
            direction = "right"
        if row["クロソイド始点R"] == "Inf":
            row["クロソイド始点R"] = float("inf")
        if row["クロソイド終点R"] == "Inf":
            row["クロソイド終点R"] = float("inf")
        type_info = typeInfo(
            type = row["形式"],
            direction = direction if row["形式"] in ("arc", "clothoid") else None,
            radius = row["曲線R"]*1000 if not pd.isna(row["曲線R"]) else None,
            start_radius = row["クロソイド始点R"]*1000 if not pd.isna(row["クロソイド始点R"]) else None,
            end_radius = row["クロソイド終点R"]*1000 if not pd.isna(row["クロソイド終点R"]) else None,
        )
        STAs.append(STA)
        Coord_infos.append(Coord_info)
        type_infos.append(type_info)
    for _, row in z_road_center_df.iterrows():
        STA = get_STA_from_STA_info(row["測点大"], row["測点小"])
        z_info = ZInfo(
            STA = STA,
            z = row["高さ"]*1000,
            pre_slope = row["前縦断勾配"]/100, # Excel上では%表示されているため100で割る
            post_slope = row["後縦断勾配"]/100,
        )
        z_infos.append(z_info)

    return RoadCenterInfo(
        plan_STAs=STAs,
        plan_Coord_infos=Coord_infos,
        z_infos=z_infos,
        type_infos=type_infos,
    )


def main(initial_or_final: str) -> None:
    if initial_or_final == "initial":
        input_dir = INITIAL_INPUT_DIR
        output_dir = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        input_dir = FINAL_INPUT_DIR
        output_dir = FINAL_OUTPUT_DIR

    plan_road_center_excel_path = input_dir / "センターライン平面線形.xlsx"
    target_names_df = read_file_to_df(
        file_path = plan_road_center_excel_path,
        sheet_name = "センターライン対象一覧",
    )
    target_name_set = set(target_names_df["名称"].dropna().unique())
    z_road_center_excel_path = input_dir / "センターライン縦断線形.xlsx"

    road_center_info_dict = {}
    for target_name in target_name_set:
        plan_road_center_df = read_file_to_df(
            file_path = plan_road_center_excel_path,
            sheet_name = target_name,
        )
        z_road_center_df = read_file_to_df(
            file_path = z_road_center_excel_path,
            sheet_name = target_name,
        ) # 同じ名前があること前提
        road_center_info = get_road_center_info(plan_road_center_df, z_road_center_df)
        road_center_info_dict[target_name] = road_center_info

    save_json_and_pickle(
        data = road_center_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.ROAD_CENTER}",
    )


if __name__ == "__main__":
    main("initial")
