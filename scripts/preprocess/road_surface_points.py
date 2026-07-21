import math
from typing import Optional

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.road_surface_schemas import (
    RoadSurfaceInfo,
    ZInfo,
    typeInfo,
)
from my_project.config.util_schemas import Point2D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.io import read_file_to_df, save_json_and_pickle


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


def get_optional_STA(row: pd.Series) -> Optional[float]:
    if "測点大" not in row.index or "測点小" not in row.index:
        return None
    if pd.isna(row["測点大"]) or pd.isna(row["測点小"]):
        return None
    return get_STA_from_STA_info(row["測点大"], row["測点小"])


def get_point_distance(point1: Point2D, point2: Point2D) -> float:
    return math.hypot(point2.x - point1.x, point2.y - point1.y)


def get_plan_segment_length(
    start_point: Point2D,
    end_point: Point2D,
    segment_type_info: typeInfo,
) -> float:
    chord_length = get_point_distance(start_point, end_point)
    if segment_type_info.type == "arc" and segment_type_info.radius not in (None, float("inf")):
        radius = abs(float(segment_type_info.radius))
        if radius > 0:
            ratio = min(chord_length / (2 * radius), 1.0)
            return radius * 2 * math.asin(ratio)
    return chord_length


def fill_missing_plan_STAs(
    STAs: list[Optional[float]],
    coord_infos: list[Point2D],
    type_infos: list[typeInfo],
) -> list[float]:
    if not STAs:
        return []
    if all(STA is not None for STA in STAs):
        return [float(STA) for STA in STAs]

    filled_STAs = [0.0] * len(STAs)
    first_known_index = next(
        (i for i, STA in enumerate(STAs) if STA is not None),
        None,
    )
    if first_known_index is not None:
        filled_STAs[first_known_index] = float(STAs[first_known_index])

        for i in range(first_known_index - 1, -1, -1):
            segment_length = get_plan_segment_length(
                coord_infos[i],
                coord_infos[i + 1],
                type_infos[i],
            )
            filled_STAs[i] = filled_STAs[i + 1] - segment_length

        start_index = first_known_index + 1
    else:
        start_index = 1

    for i in range(start_index, len(STAs)):
        if STAs[i] is not None:
            filled_STAs[i] = float(STAs[i])
        else:
            segment_length = get_plan_segment_length(
                coord_infos[i - 1],
                coord_infos[i],
                type_infos[i - 1],
            )
            filled_STAs[i] = filled_STAs[i - 1] + segment_length

    return filled_STAs


def get_road_center_info(
    plan_road_center_df: pd.DataFrame,
    z_road_center_df: Optional[pd.DataFrame],
) -> RoadSurfaceInfo:
    STAs = []
    coord_infos = []
    type_infos = []
    z_infos = []
    for _, row in plan_road_center_df.iterrows():
        if pd.isna(row["X座標"]) or pd.isna(row["Y座標"]):
            continue
        STA = get_optional_STA(row)
        STAs.append(STA)
        coord_infos.append(Point2D(x=row["X座標"] * 1000, y=row["Y座標"] * 1000))
        if pd.isna(row["形式"]):
            continue
        shape_type = get_shape_type(row["形式"])
        direction = get_curve_direction(row["向き"]) if shape_type in ("arc", "clothoid") else None
        type_infos.append(
            typeInfo(
                type=shape_type,
                direction=direction,
                radius=get_radius(row["曲線R"]),
                start_radius=get_radius(row["クロソイド始点R"]),
                end_radius=get_radius(row["クロソイド終点R"]),
            )
        )

    expected_type_count = max(len(coord_infos) - 1, 0)
    if len(type_infos) != expected_type_count:
        raise ValueError(
            "Road center plan data must have one shape type per segment. "
            f"points={len(coord_infos)}, type_infos={len(type_infos)}"
        )

    STAs = fill_missing_plan_STAs(STAs, coord_infos, type_infos)

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

    return RoadSurfaceInfo(
        plan_STAs=STAs,
        plan_Coord_infos=coord_infos,
        z_infos=z_infos,
        type_infos=type_infos,
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
        road_center_info_dict[target_name] = get_road_center_info(
            plan_road_center_df=plan_road_center_df,
            z_road_center_df=z_road_center_df,
        )

    save_json_and_pickle(
        data=road_center_info_dict,
        folder_path=output_dir,
        name=f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}",
    )


if __name__ == "__main__":
    main("initial")
