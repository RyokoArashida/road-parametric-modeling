

from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.road_surface_schemas import (
    EmbankmentPaveInfo,
    RoadSurfaceInfo,
    SlopeInfo,
    ZInfo,
    typeInfo,
)
from my_project.config.util_schemas import Point2D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_road_center_info(plan_road_center_df: pd.DataFrame, z_road_center_df: pd.DataFrame, embankment_pave_target_df: Optional[pd.DataFrame], slope_info_df: Optional[pd.DataFrame]) -> RoadSurfaceInfo:
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
    
    if embankment_pave_target_df is not None:
        embankment_pave_infos = []
        for _, row in embankment_pave_target_df.iterrows():
            name = row["全体_番号"]
            start_STA = get_STA_from_STA_info(row["始点_測点大"], row["始点_測点小"])
            end_STA = get_STA_from_STA_info(row["終点_測点大"], row["終点_測点小"])
            width = row["形状_幅"]
            raw_slope_infos = []
            for _, slope_row in slope_info_df.iterrows():
                slope_STA = get_STA_from_STA_info(slope_row["測点大"], slope_row["測点小"])
                slope = slope_row["横断勾配"]/100 # Excel上では%表示されているため100で割る
                raw_slope_infos.append((slope_STA, slope))
            # raw_slope_infosをSTAでソートする
            raw_slope_infos.sort(key=lambda x: x[0])
            # 最初に始点sta以上になるインデックスを取得
            start_index = next(i for i, (slope_STA, _) in enumerate(raw_slope_infos) if slope_STA >= start_STA)
            # 最後に終点sta以下になるインデックスを取得
            end_index = next(i for i, (slope_STA, _) in reversed(list(enumerate(raw_slope_infos))) if slope_STA <= end_STA)
            start_slope = raw_slope_infos[start_index - 1][1] + (raw_slope_infos[start_index][1] - raw_slope_infos[start_index - 1][1]) * (start_STA - raw_slope_infos[start_index - 1][0]) / (raw_slope_infos[start_index][0] - raw_slope_infos[start_index - 1][0])
            end_slope = raw_slope_infos[end_index][1] + (raw_slope_infos[end_index + 1][1] - raw_slope_infos[end_index][1]) * (end_STA - raw_slope_infos[end_index][0]) / (raw_slope_infos[end_index + 1][0] - raw_slope_infos[end_index][0])
            slope_infos = [SlopeInfo(STA=start_STA, slope=start_slope)]
            # 間の点の数
            mid_points_count = end_index - start_index + 1
            if mid_points_count > 0:
                for i in range(start_index, end_index + 1):
                    slope_STA, slope = raw_slope_infos[i]
                    slope_infos.append(SlopeInfo(STA=slope_STA, slope=slope))
            slope_infos.append(SlopeInfo(STA=end_STA, slope=end_slope))
            embankment_pave_info = EmbankmentPaveInfo(
                slope_infos=slope_infos,
                width=width,
            )
            embankment_pave_infos.append(embankment_pave_info)

        return RoadSurfaceInfo(
            plan_STAs=STAs,
            plan_Coord_infos=Coord_infos,
            z_infos=z_infos,
            type_infos=type_infos,
            embankment_pave_infos=embankment_pave_infos,
        )

    return RoadSurfaceInfo(
        plan_STAs=STAs,
        plan_Coord_infos=Coord_infos,
        z_infos=z_infos,
        type_infos=type_infos,
    )


def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    plan_road_center_excel_path = input_dir / "センターライン平面線形.xlsx"
    target_names_df = read_file_to_df(
        file_path = plan_road_center_excel_path,
        sheet_name = "センターライン対象一覧",
    )
    target_name_set = set(target_names_df["名称"].dropna().unique())
    z_road_center_excel_path = input_dir / "センターライン縦断線形.xlsx"
    embankment_pave_excel_path = input_dir / "土工部舗装横断線形.xlsx"

    embankment_pave_master_df = read_file_to_df(
        file_path = embankment_pave_excel_path,
        sheet_name = "土工部舗装対象一覧",
        header = [0,1]
    )


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
        # embankment_pave_master_dfの全体_名称列がtarget_nameと一致する行を抽出
        embankment_pave_target_df = embankment_pave_master_df[
            embankment_pave_master_df["全体_名称"] == target_name
        ]
        if embankment_pave_target_df.empty:
            embankment_pave_target_df = None
            slope_info_df = None
        else:
            slope_info_df = read_file_to_df(
                file_path = embankment_pave_excel_path,
                sheet_name = target_name,
            )
        road_center_info = get_road_center_info(plan_road_center_df, z_road_center_df, embankment_pave_target_df, slope_info_df)
        road_center_info_dict[target_name] = road_center_info

        

    save_json_and_pickle(
        data = road_center_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}",
    )


if __name__ == "__main__":
    main("initial")
