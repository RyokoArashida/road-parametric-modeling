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
from my_project.config.util_schemas import MonoSlope, Point2D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


def get_embankment_excel_path(input_dir):
    candidates = [
        input_dir / "土工部土工線形.xlsx",
        input_dir / "土工部横断線形.xlsx",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Embankment alignment Excel was not found: {candidates}")


def get_shape_type(value: str) -> str:
    if value == "直線":
        return "line"
    if value == "曲線":
        return "arc"
    if value == "クロソイド":
        return "clothoid"
    raise ValueError(f"Unknown road center shape type: {value}")


def get_curve_direction(value):
    if value == "左":
        return "left"
    if value == "右":
        return "right"
    if pd.isna(value):
        return None
    raise ValueError(f"Unknown curve direction: {value}")


def get_radius(value):
    if value == "Inf":
        return float("inf")
    if pd.isna(value):
        return None
    return value * 1000


def get_slope_infos(
    start_STA: float,
    end_STA: float,
    slope_info_df: pd.DataFrame,
) -> list[SlopeInfo]:
    raw_slope_infos = []
    for _, slope_row in slope_info_df.iterrows():
        slope_STA = get_STA_from_STA_info(slope_row["測点大"], slope_row["測点小"])
        raw_slope_infos.append((slope_STA, MonoSlope(slope_row["横断勾配"])))
    raw_slope_infos.sort(key=lambda x: x[0])
    if len(raw_slope_infos) < 2:
        raise ValueError("Need at least 2 embankment cross slope rows")

    start_index = next(i for i, (slope_STA, _) in enumerate(raw_slope_infos) if slope_STA >= start_STA)
    end_index = next(i for i, (slope_STA, _) in reversed(list(enumerate(raw_slope_infos))) if slope_STA <= end_STA)

    def interpolate_slope(STA: float, i0: int, i1: int) -> MonoSlope:
        STA0, slope0 = raw_slope_infos[i0]
        STA1, slope1 = raw_slope_infos[i1]
        if STA1 == STA0:
            return slope0
        ratio = (STA - STA0) / (STA1 - STA0)
        return MonoSlope(slope0.value + (slope1.value - slope0.value) * ratio)

    start_slope = interpolate_slope(start_STA, start_index - 1, start_index)
    end_slope = interpolate_slope(end_STA, end_index, end_index + 1)

    slope_infos = [SlopeInfo(STA=start_STA, slope=start_slope)]
    for i in range(start_index, end_index + 1):
        slope_STA, slope = raw_slope_infos[i]
        slope_infos.append(SlopeInfo(STA=slope_STA, slope=slope))
    slope_infos.append(SlopeInfo(STA=end_STA, slope=end_slope))
    return slope_infos


def get_road_center_info(
    plan_road_center_df: pd.DataFrame,
    z_road_center_df: Optional[pd.DataFrame],
    embankment_target_df: Optional[pd.DataFrame],
    slope_info_df: Optional[pd.DataFrame],
) -> RoadSurfaceInfo:
    STAs = []
    coord_infos = []
    type_infos = []
    z_infos = []
    for _, row in plan_road_center_df.iterrows():
        if pd.isna(row["形式"]):
            continue
        STA = get_STA_from_STA_info(row["測点大"], row["測点小"])
        shape_type = get_shape_type(row["形式"])
        direction = get_curve_direction(row["向き"]) if shape_type in ("arc", "clothoid") else None
        STAs.append(STA)
        coord_infos.append(Point2D(x=row["X座標"] * 1000, y=row["Y座標"] * 1000))
        type_infos.append(
            typeInfo(
                type=shape_type,
                direction=direction,
                radius=get_radius(row["曲線R"]),
                start_radius=get_radius(row["クロソイド始点R"]),
                end_radius=get_radius(row["クロソイド終点R"]),
            )
        )

    if z_road_center_df is not None:
        for _, row in z_road_center_df.iterrows():
            if pd.isna(row["測点大"]) or pd.isna(row["測点小"]):
                continue
            z_infos.append(
                ZInfo(
                    STA=get_STA_from_STA_info(row["測点大"], row["測点小"]),
                    z=row["高さ"] * 1000,
                    pre_slope=row["前縦断勾配"] / 100,
                    post_slope=row["後縦断勾配"] / 100,
                )
            )

    if embankment_target_df is None:
        return RoadSurfaceInfo(
            plan_STAs=STAs,
            plan_Coord_infos=coord_infos,
            z_infos=z_infos,
            type_infos=type_infos,
        )

    if slope_info_df is None:
        raise ValueError("slope_info_df is required when embankment targets exist")

    embankment_pave_infos = []
    for _, row in embankment_target_df.iterrows():
        start_STA = get_STA_from_STA_info(row["舗装始点_測点大"], row["舗装始点_測点小"])
        end_STA = get_STA_from_STA_info(row["舗装終点_測点大"], row["舗装終点_測点小"])
        embankment_pave_infos.append(
            EmbankmentPaveInfo(
                slope_infos=get_slope_infos(start_STA, end_STA, slope_info_df),
                width=row["形状_幅"],
            )
        )

    return RoadSurfaceInfo(
        plan_STAs=STAs,
        plan_Coord_infos=coord_infos,
        z_infos=z_infos,
        type_infos=type_infos,
        embankment_pave_infos=embankment_pave_infos,
    )


def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    plan_road_center_excel_path = input_dir / "センターライン平面線形.xlsx"
    target_names_df = read_file_to_df(
        file_path=plan_road_center_excel_path,
        sheet_name="センターライン対象一覧",
    )
    target_name_set = set(target_names_df["名称"].dropna().unique())
    z_road_center_excel_path = input_dir / "センターライン縦断線形.xlsx"
    embankment_excel_path = get_embankment_excel_path(input_dir)

    embankment_master_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="土工部対象一覧",
        header=[0, 1],
    )
    slope_info_df = read_file_to_df(
        file_path=embankment_excel_path,
        sheet_name="舗装横断勾配",
    )

    road_center_info_dict = {}
    for target_name in target_name_set:
        plan_road_center_df = read_file_to_df(
            file_path=plan_road_center_excel_path,
            sheet_name=target_name,
        )
        z_road_center_df = None
        if z_road_center_excel_path.exists():
            try:
                z_road_center_df = read_file_to_df(
                    file_path=z_road_center_excel_path,
                    sheet_name=target_name,
                )
            except ValueError as exc:
                if "Worksheet" not in str(exc):
                    raise
        embankment_target_df = embankment_master_df[
            embankment_master_df["全体_名称"] == target_name
        ]
        if embankment_target_df.empty:
            embankment_target_df = None
            target_slope_info_df = None
        else:
            target_slope_info_df = slope_info_df[slope_info_df["名称"] == target_name]
        road_center_info_dict[target_name] = get_road_center_info(
            plan_road_center_df=plan_road_center_df,
            z_road_center_df=z_road_center_df,
            embankment_target_df=embankment_target_df,
            slope_info_df=target_slope_info_df,
        )

    save_json_and_pickle(
        data=road_center_info_dict,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}",
    )


if __name__ == "__main__":
    main("initial")
