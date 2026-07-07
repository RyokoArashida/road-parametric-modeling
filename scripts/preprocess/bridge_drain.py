
import math
from numbers import Number
from typing import Optional, Union

import pandas as pd

from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs
from my_project.config.schemas.bridge_drainage_schemas import (
    DrainageInfo,
    DrainagePoint,
    PipeInfo,
)
from my_project.config.schemas.superstructure_schemas import (
    CoordInfo,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle
from my_project.utils.geometry.points import get_polyline_info_from_coord_info, get_plan_offset_and_z_delta
from my_project.utils.dataframe import get_single_value


def add_target_point_name(
    target_point_name_dict: dict[str, set[str]],
    bridge_name: str,
    point_name: str,
) -> None:
    if pd.isna(bridge_name) or pd.isna(point_name):
        return
    if bridge_name not in target_point_name_dict:
        target_point_name_dict[bridge_name] = set()
    target_point_name_dict[bridge_name].add(point_name)


def add_target_point_alias(
    output_name_by_point_name_dict: dict[str, dict[str, str]],
    bridge_name: str,
    point_name: str,
    output_name: str,
) -> None:
    if pd.isna(bridge_name) or pd.isna(point_name) or pd.isna(output_name):
        return
    if bridge_name not in output_name_by_point_name_dict:
        output_name_by_point_name_dict[bridge_name] = {}
    output_name_by_point_name_dict[bridge_name][point_name] = output_name

def build_target_point_polyline_dict(
    coord_dict: dict[str, list[CoordInfo]],
    orthogonal_basis_df: pd.DataFrame,
    y_location_df: pd.DataFrame,
    main_df: pd.DataFrame,
    road_df: pd.DataFrame,
    substructure_df: pd.DataFrame,
) -> dict:
    target_point_name_dict = {}
    output_name_by_point_name_dict = {}
    target_specs = [
        (y_location_df, "橋梁名", "基準線"),
        (main_df, "全体_橋梁名", "全体_x0基準"),
        (road_df, "全体_橋梁名", "全体_x0基準"),
        (substructure_df, "全体_橋梁名", "全体_x0基準"),
    ]
    for target_df, bridge_col, point_col in target_specs:
        for _, row in target_df.iterrows():
            add_target_point_name(
                target_point_name_dict = target_point_name_dict,
                bridge_name = row[bridge_col],
                point_name = row[point_col],
            )

    for _, row in orthogonal_basis_df.iterrows():
        add_target_point_name(
            target_point_name_dict=target_point_name_dict,
            bridge_name=row["橋梁名"],
            point_name=row["中心"],
        )
        add_target_point_alias(
            output_name_by_point_name_dict=output_name_by_point_name_dict,
            bridge_name=row["橋梁名"],
            point_name=row["中心"],
            output_name="CL",
        )

    return {
        bridge_name: get_polyline_info_from_coord_info(
            coord_infos = coord_dict[bridge_name],
            target_point_name_list = target_point_name_list,
            output_name_by_point_name = output_name_by_point_name_dict.get(bridge_name),
        )
        for bridge_name, target_point_name_list in target_point_name_dict.items()
    }


def get_pipeinfo(
    row: pd.Series,
    yobikei_gaikei_df: pd.DataFrame,
):
    super_sub = row["全体_上下部工"] if "全体_上下部工" in row and not pd.isna(row["全体_上下部工"]) else None
    pipetype = row["全体_管種"]
    pipe_name = f"{super_sub}_{pipetype}" if super_sub is not None else pipetype
    material = row["規格_素材"]
    if material == "VP":
        yobikei = row["規格_呼び径"]
        yobikei_row = yobikei_gaikei_df[yobikei_gaikei_df["呼び径"] == yobikei]
        diameter = get_single_value(yobikei_row["外径"], f"VP管 呼び径={yobikei} の外径")
        thickness = (diameter - yobikei) / 2
    else:
        diameter = row["規格_外径"] if "規格_外径" in row and not pd.isna(row["規格_外径"]) else None
        thickness = row["規格_厚さ"] if "規格_厚さ" in row and not pd.isna(row["規格_厚さ"]) else None
    width = row["規格_幅"] if "規格_幅" in row and not pd.isna(row["規格_幅"]) else None
    height = row["規格_高さ"] if "規格_高さ" in row and not pd.isna(row["規格_高さ"]) else None
    pipeinfo = PipeInfo(
        name = pipe_name,
        material = material,
        diameter = diameter,
        thickness = thickness,
        width = width,
        height = height,
    )
    return pipeinfo

def get_x(
    x: Union[float, str],
    start_point: DrainagePoint,
    end_point: DrainagePoint,
):
    if x == "s":
        return start_point.x_base_polyline, start_point.x_offset
    elif x == "e":
        return end_point.x_base_polyline, end_point.x_offset
    else:
        return None, float(x)

def get_y_location(
    bridge_name: str,
    y_location_name: str,
    y_location_df: pd.DataFrame,
):
    y_location_row = y_location_df[
        (y_location_df["橋梁名"] == bridge_name) & (y_location_df["名称"] == y_location_name)
    ]
    context = f"y絶対位置 {bridge_name}/{y_location_name}"
    y_base_polyline = get_single_value(y_location_row["基準線"], f"{context} 基準線")
    y_base_CG_name = get_single_value(y_location_row["基準CG"], f"{context} 基準CG")
    y_offset = get_single_value(y_location_row["離隔"], f"{context} 離隔")
    return y_base_polyline, y_base_CG_name, y_offset

def get_y(
    y: Union[float, str],
    start_point: DrainagePoint,
    end_point: DrainagePoint,
    y_location_df: pd.DataFrame,
    bridge_name: str,
):
    if y == "s":
        return start_point.y_base_polyline, start_point.y_base_CG_name, start_point.y_offset
    elif y == "e":
        return end_point.y_base_polyline, end_point.y_base_CG_name, end_point.y_offset
    else:
        return get_y_location(
            bridge_name = bridge_name,
            y_location_name = y,
            y_location_df = y_location_df,
        )

def get_none_point_info():
    return DrainagePoint(
        y_base_polyline = None,
        y_base_CG_name = None,
        y_offset = None,
        y_adj_ratio = None,
        x_base_polyline = None,
        x_zero_base_polyline = None,
        x_offset = None,
        z = None,
    )


def get_road_start_y_name(row: pd.Series, drainage_name: str) -> str:
    if "始点_y名称" in row and not pd.isna(row["始点_y名称"]):
        return row["始点_y名称"]
    return drainage_name


def split_detail_points(
    detail_rows: pd.DataFrame,
    yobikei_gaikei_df: pd.DataFrame,
    *,
    point_axis: str,
    offset_axis: str,
    slope_axis: str,
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    forward_points_raw = []
    backward_points_raw = []
    pipe_infos = []
    point_index = 0
    forward = True

    for _, details_row in detail_rows.iterrows():
        pipe_info = get_pipeinfo(details_row, yobikei_gaikei_df)
        start_point_index = point_index
        for i in range(1, 4):
            point_col = f"折れ点{i}_{point_axis}"
            offset_col = f"~折れ点{i}_{offset_axis}"
            if not pd.isna(details_row[point_col]):
                point_index += 1
                point_value = details_row[point_col]
                z_slope = float(details_row[f"~折れ点{i}_{slope_axis}傾き"]) if not pd.isna(details_row[f"~折れ点{i}_{slope_axis}傾き"]) else None
                z_abs = float(details_row[f"~折れ点{i}_落ち"]) if not pd.isna(details_row[f"~折れ点{i}_落ち"]) else None
                if details_row[offset_col] == "調整":
                    offset = "adjustment"
                    ratio = 1.0
                    forward = False
                else:
                    offset = float(details_row[offset_col]) if not pd.isna(details_row[offset_col]) else 0.0
                    ratio = None
                if forward:
                    forward_points_raw.append((point_value, offset, z_slope, z_abs, ratio))
                else:
                    backward_points_raw.append((point_value, offset, z_slope, z_abs, ratio))

        vector_col = f"ベクトル_{point_axis}"
        if not pd.isna(details_row[vector_col]):
            forward = False
            point_value = details_row[vector_col]
            all_length = float(details_row["ベクトル_全体長さ"])
            this_length = float(details_row["ベクトル_対象長さ"])
            ratio = this_length / all_length
            point_index += 1
            backward_points_raw.append((point_value, "vector", None, None, ratio))

        pipe_infos.append((start_point_index, point_index, pipe_info))

    return forward_points_raw, backward_points_raw, pipe_infos


def solve_offsets_from_start_end(
    raw_points: list[tuple],
    start_offset: float,
    start_z: float,
    end_offset: float,
    end_z: float,
) -> tuple[list[float], list[float], list[bool], list[Optional[float]]]:
    offsets = [None] * len(raw_points)
    zs = [None] * len(raw_points)
    is_vector = [False] * len(raw_points)
    ratios = [None] * len(raw_points)
    vector_indices = [i for i, (_, offset, _, _, _) in enumerate(raw_points) if offset == "vector"]
    adjustment_indices = [i for i, (_, offset, _, _, _) in enumerate(raw_points) if offset == "adjustment"]

    if vector_indices:
        first_vector = vector_indices[0]
        last_vector = vector_indices[-1]
        current_offset = start_offset
        current_z = start_z
        for i in range(first_vector):
            _, raw_offset, z_slope, z_abs, _ = raw_points[i]
            plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
            current_offset += plan_offset
            current_z += z_delta
            offsets[i] = current_offset
            zs[i] = current_z

        next_offset = end_offset
        next_z = end_z
        for i in range(len(raw_points) - 1, last_vector, -1):
            offsets[i] = next_offset
            zs[i] = next_z
            _, raw_offset, z_slope, z_abs, _ = raw_points[i]
            plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
            next_offset -= plan_offset
            next_z -= z_delta

        for i in vector_indices:
            _, _, _, _, ratio = raw_points[i]
            is_vector[i] = True
            ratios[i] = ratio
            offsets[i] = current_offset + (next_offset - current_offset) * ratio
            zs[i] = current_z + (next_z - current_z) * ratio

        return offsets, zs, is_vector, ratios

    if len(adjustment_indices) > 1:
        raise ValueError("adjustment は1つまでしか扱えません")

    if not adjustment_indices:
        current_offset = start_offset
        current_z = start_z
        for i, (_, raw_offset, z_slope, z_abs, _) in enumerate(raw_points):
            plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
            current_offset += plan_offset
            current_z += z_delta
            offsets[i] = current_offset
            zs[i] = current_z
        return offsets, zs, is_vector, ratios

    adjustment_index = adjustment_indices[0]
    current_offset = start_offset
    current_z = start_z
    for i in range(adjustment_index):
        _, raw_offset, z_slope, z_abs, _ = raw_points[i]
        plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
        current_offset += plan_offset
        current_z += z_delta
        offsets[i] = current_offset
        zs[i] = current_z

    current_offset = end_offset
    current_z = end_z
    for i in range(len(raw_points) - 1, adjustment_index - 1, -1):
        offsets[i] = current_offset
        zs[i] = current_z
        if i == adjustment_index:
            break
        _, raw_offset, z_slope, z_abs, _ = raw_points[i]
        plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
        current_offset -= plan_offset
        current_z -= z_delta

    return offsets, zs, is_vector, ratios


def solve_offsets_from_end(
    raw_points: list[tuple],
    end_offset: float,
    end_z: float,
) -> tuple[list[float], list[float], list[bool], list[Optional[float]], float, float]:
    offsets = [None] * len(raw_points)
    zs = [None] * len(raw_points)
    is_vector = [False] * len(raw_points)
    ratios = [None] * len(raw_points)

    current_offset = end_offset
    current_z = end_z
    for i in range(len(raw_points) - 1, -1, -1):
        _, raw_offset, z_slope, z_abs, ratio = raw_points[i]
        offsets[i] = current_offset
        zs[i] = current_z
        if raw_offset == "vector":
            is_vector[i] = True
            ratios[i] = ratio
            continue
        if raw_offset == "adjustment":
            continue

        plan_offset, z_delta = get_plan_offset_and_z_delta(float(raw_offset), z_slope, z_abs)
        current_offset -= plan_offset
        current_z -= z_delta

    return offsets, zs, is_vector, ratios, current_offset, current_z


def get_special_split_index(raw_points: list[tuple]) -> Optional[int]:
    special_indices = [
        i for i, (_, offset, _, _, _) in enumerate(raw_points)
        if offset in ("adjustment", "vector")
    ]
    if not special_indices:
        return None
    return special_indices[0]


def choose_base_from_split(
    index: int,
    split_index: Optional[int],
    start_base,
    end_base,
):
    if split_index is None or index < split_index:
        return start_base
    return end_base


def get_main_drainage_info(
    row: pd.Series,
    y_location_df: pd.DataFrame,
    main_detail_df: pd.DataFrame,
    yobikei_gaikei_df: pd.DataFrame,
) -> DrainageInfo:
    bridge_name = row["全体_橋梁名"]
    drainage_name = row["全体_排水名称"]
    x0_base = row["全体_x0基準"]
    start_x0_offset = row["始点_x0距離"]
    end_x0_offset = row["終点_x0距離"]
    start_y_name = row["始点_y名称"]
    end_y_name = row["終点_y名称"]
    start_z = row["始点_高さ"] * 1000
    end_z = row["終点_高さ"] * 1000

    start_y_base_polyline, start_y_base_CG_name, start_y_offset = get_y_location(
        bridge_name = bridge_name,
        y_location_name = start_y_name,
        y_location_df = y_location_df,
    )
    start_point = DrainagePoint(
        y_base_polyline = start_y_base_polyline,
        y_base_CG_name = start_y_base_CG_name,
        y_offset = start_y_offset,
        y_adj_ratio = None,
        x_base_polyline = x0_base,
        x_zero_base_polyline = None,
        x_offset = start_x0_offset,
        z = start_z,
    )

    end_y_base_polyline, end_y_base_CG_name, end_y_offset = get_y_location(
        bridge_name = bridge_name,
        y_location_name = end_y_name,
        y_location_df = y_location_df,
    )
    end_point = DrainagePoint(
        y_base_polyline = end_y_base_polyline,
        y_base_CG_name = end_y_base_CG_name,
        y_offset = end_y_offset,
        y_adj_ratio = None,
        x_base_polyline = x0_base,
        x_zero_base_polyline = None,
        x_offset = end_x0_offset,
        z = end_z,
    )

    details_rows = main_detail_df[
        (main_detail_df["全体_橋梁名"] == bridge_name) & (main_detail_df["全体_排水名称"] == drainage_name)
    ]

    forward_point_raw, backward_points_raw, pipe_infos = split_detail_points(
        details_rows,
        yobikei_gaikei_df,
        point_axis="x",
        offset_axis="y",
        slope_axis="yz",
    )

    raw_points = forward_point_raw + backward_points_raw
    if not raw_points:
        raise ValueError(f"本管詳細に折れ点がありません: {bridge_name}/{drainage_name}")

    solved_y_offsets, solved_zs, is_vector, ratios = solve_offsets_from_start_end(
        raw_points=raw_points,
        start_offset=start_point.y_offset,
        start_z=start_point.z,
        end_offset=end_point.y_offset,
        end_z=end_point.z,
    )
    split_index = get_special_split_index(raw_points)

    points = [start_point]
    for i, (x, _, _, _, _) in enumerate(raw_points):
        x_base_polyline, x_offset = get_x(x, start_point, end_point)
        y_base_polyline, y_base_CG_name = choose_base_from_split(
            i,
            split_index,
            (start_point.y_base_polyline, start_point.y_base_CG_name),
            (end_point.y_base_polyline, end_point.y_base_CG_name),
        )
        if is_vector[i] and not math.isclose(ratios[i], 1.0):
            y_offset = "adjustment"
            y_adj_ratio = ratios[i]
        else:
            y_offset = solved_y_offsets[i]
            y_adj_ratio = None
        points.append(DrainagePoint(
            y_base_polyline = y_base_polyline,
            y_base_CG_name = y_base_CG_name,
            y_offset = y_offset,
            y_adj_ratio = y_adj_ratio,
            x_base_polyline = x0_base,
            x_zero_base_polyline = None,
            x_offset = x_offset,
            z = solved_zs[i],
        ))
    drainage_info = DrainageInfo(
        bridge_name = bridge_name,
        drainage_name = drainage_name,
        points = points,
        pipes = pipe_infos,
    )
    return drainage_info

def get_road_drainage_info(
    row: pd.Series,
    y_location_df: pd.DataFrame,
    road_detail_df: pd.DataFrame,
    yobikei_gaikei_df: pd.DataFrame,
    main_drainage_info_dict: dict[tuple[str, str], DrainageInfo],
    road_drainage_info_dict: Optional[dict[tuple[str, str], DrainageInfo]],
) -> DrainageInfo:
    bridge_name = row["全体_橋梁名"]
    drainage_name = row["全体_排水名称"]
    is_connection = False
    if not pd.isna(row["終点_本管名称"]):
        start_y_name = get_road_start_y_name(row, drainage_name)
        start_y_base_polyline, start_y_base_CG_name, start_y_offset = get_y_location(
            bridge_name=bridge_name,
            y_location_name=start_y_name,
            y_location_df=y_location_df,
        )
        start_point = DrainagePoint(
            y_base_polyline=start_y_base_polyline,
            y_base_CG_name=start_y_base_CG_name,
            y_offset=start_y_offset,
            y_adj_ratio=None,
            x_base_polyline=None,
            x_zero_base_polyline=None,
            x_offset=None,
            z=None,
        )
        end_point_main_drainage_name = row["終点_本管名称"]
        end_point_main_drainage_se = row["終点_本管始終"]
        main_drainage_key = (bridge_name, end_point_main_drainage_name)
        if main_drainage_key not in main_drainage_info_dict:
            available_names = sorted(
                str(name) for bridge, name in main_drainage_info_dict
                if bridge == bridge_name
            )
            raise ValueError(
                f"路面排水 {bridge_name}/{drainage_name} が存在しない本管 "
                f"{end_point_main_drainage_name} を参照しています。"
                f"利用可能な本管: {available_names}"
            )
        main_drainage_info = main_drainage_info_dict[main_drainage_key]
        if end_point_main_drainage_se == "s":
            end_point = main_drainage_info.points[0]
        elif end_point_main_drainage_se == "e":
            end_point = main_drainage_info.points[-1]
        else:
            raise ValueError("本管始終の値が不正")
    elif not pd.isna(row["全体_x0基準"]):
        start_y_name = get_road_start_y_name(row, drainage_name)
        start_y_base_polyline, start_y_base_CG_name, start_y_offset = get_y_location(
            bridge_name=bridge_name,
            y_location_name=start_y_name,
            y_location_df=y_location_df,
        )
        x0_base = row["全体_x0基準"]
        start_point = DrainagePoint(
            y_base_polyline=start_y_base_polyline,
            y_base_CG_name=start_y_base_CG_name,
            y_offset=start_y_offset,
            y_adj_ratio=None,
            x_base_polyline=x0_base,
            x_zero_base_polyline=None,
            x_offset=None,
            z=None,
        )
        end_y_base_polyline, end_y_base_CG_name, end_y_offset = get_y_location(
            bridge_name = bridge_name,
            y_location_name = drainage_name,
            y_location_df = y_location_df,
        )
        end_x0_offset = row["終点_x0距離"]
        end_z = row["終点_高さ"] * 1000
        end_point = DrainagePoint(
            y_base_polyline = end_y_base_polyline,
            y_base_CG_name = end_y_base_CG_name,
            y_offset = end_y_offset,
            y_adj_ratio = None,
            x_base_polyline = x0_base,
            x_zero_base_polyline = None,
            x_offset = end_x0_offset,
            z = end_z,
        )
    elif not pd.isna(row["つなぎ_始点"]):
        is_connection = True
        start_point_road_drainage_name = row["つなぎ_始点"]
        end_point_road_drainage_name = row["つなぎ_終点"]
        if road_drainage_info_dict is None:
            raise ValueError("road_drainage_info_dictが必要")
        start_point = road_drainage_info_dict[(bridge_name, start_point_road_drainage_name)].points[-1] # 終点でつなぐので。
        end_point = road_drainage_info_dict[(bridge_name, end_point_road_drainage_name)].points[-1] # 終点でつなぐので。
    else:
        raise ValueError("終点の情報が不足")
    x_base_polyline = end_point.x_base_polyline

    details_rows = road_detail_df[
        (road_detail_df["全体_橋梁名"] == bridge_name) & (road_detail_df["全体_排水名称"] == drainage_name)
    ]

    forward_point_raw, backward_points_raw, pipe_infos = split_detail_points(
        details_rows,
        yobikei_gaikei_df,
        point_axis="y",
        offset_axis="x",
        slope_axis="xz",
    )

    raw_points = forward_point_raw + backward_points_raw
    if not raw_points:
        raise ValueError(f"路面排水詳細に折れ点がありません: {bridge_name}/{drainage_name}")
    connection_split_index = get_special_split_index(raw_points) if is_connection else None

    if start_point.x_offset is None:
        solved_x_offsets, solved_zs, is_vector, ratios, start_x_offset, start_z = solve_offsets_from_end(
            raw_points=raw_points,
            end_offset=end_point.x_offset,
            end_z=end_point.z,
        )
        start_point = DrainagePoint(
            y_base_polyline=start_point.y_base_polyline,
            y_base_CG_name=start_point.y_base_CG_name,
            y_offset=start_point.y_offset,
            y_adj_ratio=start_point.y_adj_ratio,
            x_base_polyline=x_base_polyline,
            x_zero_base_polyline=start_point.x_zero_base_polyline,
            x_offset=start_x_offset,
            z=start_z,
        )
    else:
        solved_x_offsets, solved_zs, is_vector, ratios = solve_offsets_from_start_end(
            raw_points=raw_points,
            start_offset=start_point.x_offset,
            start_z=start_point.z,
            end_offset=end_point.x_offset,
            end_z=end_point.z,
        )

    points = [start_point]
    for i, (y, _, _, _, _) in enumerate(raw_points):
        y_base_polyline, y_base_CG_name, y_offset = get_y(y, start_point, end_point, y_location_df, bridge_name)
        if is_connection and connection_split_index is not None and i < connection_split_index:
            point_x_base_polyline = start_point.x_base_polyline
        elif is_connection:
            point_x_base_polyline = end_point.x_base_polyline
        else:
            point_x_base_polyline = x_base_polyline
        if is_vector[i] and not math.isclose(ratios[i], 1.0):
            x_offset = "adjustment"
            y_adj_ratio = ratios[i]
        else:
            x_offset = solved_x_offsets[i]
            y_adj_ratio = None
        points.append(DrainagePoint(
            y_base_polyline = y_base_polyline,
            y_base_CG_name = y_base_CG_name,
            y_offset = y_offset,
            y_adj_ratio = y_adj_ratio,
            x_base_polyline = point_x_base_polyline,
            x_zero_base_polyline = None,
            x_offset = x_offset,
            z = solved_zs[i],
        ))
    drainage_info = DrainageInfo(
        bridge_name = bridge_name,
        drainage_name = drainage_name,
        points = points,
        pipes = pipe_infos,
        is_connection = is_connection,
    )
    return drainage_info

def get_substructure_drainage_info(
    row: pd.Series,
    y_location_df: pd.DataFrame,
    substructure_detail_df: pd.DataFrame,
    yobikei_gaikei_df: pd.DataFrame,
    main_drainage_info_dict: dict[tuple[str, str], DrainageInfo],
    road_drainage_info_dict: dict[tuple[str, str], DrainageInfo],
) -> DrainageInfo:
    bridge_name = row["全体_橋梁名"]
    drainage_name = row["全体_下部工名称"]
    x0_base = row["全体_x0基準"]
    x0_offset = row["全体_x0距離"]
    end_point = get_none_point_info() # 終点は自由
    end_point_z = row["終点_高さ"] * 1000
    if not pd.isna(row["始点_本管名称"]):
        start_point_main_drainage_name = row["始点_本管名称"]
        start_point_main_drainage_se = row["始点_本管始終"]
        main_drainage_info = main_drainage_info_dict[(bridge_name, start_point_main_drainage_name)]
        if start_point_main_drainage_se == "s":
            start_point = main_drainage_info.points[0]
        elif start_point_main_drainage_se == "e":
            start_point = main_drainage_info.points[-1]
        else:
            raise ValueError("本管始終の値が不正")
    elif not pd.isna(row["始点_路面排水名称"]):
        start_point_road_drainage_name = row["始点_路面排水名称"]
        start_point_road_drainage_se = row["始点_路面排水始終"]
        if start_point_road_drainage_se == "s":
            start_point = road_drainage_info_dict[(bridge_name, start_point_road_drainage_name)].points[0]
        elif start_point_road_drainage_se == "e":
            start_point = road_drainage_info_dict[(bridge_name, start_point_road_drainage_name)].points[-1]
        else:
            raise ValueError("路面排水始終の値が不正")
    else:
        raise ValueError("始点の情報が不足")

    start_point_z = start_point.z
    all_height = start_point_z - end_point_z

    details_rows = substructure_detail_df[
        (substructure_detail_df["全体_橋梁名"] == bridge_name) & (substructure_detail_df["全体_下部工名称"] == drainage_name)
    ]

    point_raw = []
    pipe_infos = []
    point_index = 0
    z_sum = 0
    for _, details_row in details_rows.iterrows():
        pipe_info = get_pipeinfo(details_row, yobikei_gaikei_df)
        start_point_index = point_index
        for i in range(1, 4):
            if not pd.isna(details_row[f"折れ点{i}_y"]):
                point_index += 1
                x = details_row[f"折れ点{i}_x"]
                y = details_row[f"折れ点{i}_y"]
                if details_row[f"~折れ点{i}_落ち"] == "調整":
                    z = "adjustment"
                else:
                    z = float(details_row[f"~折れ点{i}_落ち"])
                    z_sum += z
                point_raw.append((x,y,z))
        pipe_infos.append((start_point_index, point_index, pipe_info))

    # adjustmentがある場合は、他の数値の高さの合計をもとに調整値を計算する
    if any(z == "adjustment" for _, _, z in point_raw):
        if not all(isinstance(z, Number) or z == "adjustment" for _, _, z in point_raw):
            raise ValueError("数値と調整以外の値が混在している")
        if z_sum >= all_height:
            raise ValueError("調整の基準となる数値の合計が全体の高さ以上になっている")
        adjustment_value = all_height - z_sum
        point_raw = [(x, y, adjustment_value if z == "adjustment" else z) for x, y, z in point_raw]

    start_z = start_point.z
    points = [start_point]
    for x, y, z, in point_raw:
        x_base_polyline, x_offset = get_x(x, start_point, end_point)
        x_zero_base_polyline = None
        if x_base_polyline is None:
            x_base_polyline = start_point.x_base_polyline
            x_zero_base_polyline = x0_base
            x_offset = x + x0_offset
        y_base_polyline, y_base_CG_name, y_offset = get_y(y, start_point, end_point, y_location_df, bridge_name)
        start_z -= z
        point = DrainagePoint(
            y_base_polyline = y_base_polyline,
            y_base_CG_name = y_base_CG_name,
            y_offset = y_offset,
            y_adj_ratio = None,
            x_base_polyline = x_base_polyline,
            x_zero_base_polyline = x_zero_base_polyline,
            x_offset = x_offset,
            z = start_z,
        )
        points.append(point)

    drainage_info = DrainageInfo(
        bridge_name = bridge_name,
        drainage_name = drainage_name,
        points = points,
        pipes = pipe_infos,
    )
    return drainage_info


def main(initial_or_final: str) -> None:
    input_dir, output_dir = get_input_output_dirs(initial_or_final)

    drainage_excel_path = input_dir / "橋梁排水諸元.xlsm"

    orthogonal_basis_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "直交面の基準",
    )

    y_location_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "y絶対位置",
    )

    main_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "本管",
        header=[0,1]
    )

    main_detail_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "本管詳細",
        header=[0,1]
    )

    road_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "路面排水",
        header=[0,1]
    )

    road_detail_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "路面排水詳細",
        header=[0,1]
    )

    substructure_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "下部工排水",
        header=[0,1]
    )

    substructure_detail_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "下部工排水詳細",
        header=[0,1]
    )

    yobikei_gaikei_df = read_file_to_df(
        file_path = drainage_excel_path,
        sheet_name = "VP管呼び径と外径",
    )

    coord_dict = load_from_pickle(
        file_path = output_dir / f"{Filenames.INPUT}_{Filenames.SUPERSTRUCTURE}_{Filenames.COMMON}.pickle",
    )

    # まずcoord情報を整理
    target_point_name_dict = build_target_point_polyline_dict(
        coord_dict = coord_dict,
        orthogonal_basis_df = orthogonal_basis_df,
        y_location_df = y_location_df,
        main_df = main_df,
        road_df = road_df,
        substructure_df = substructure_df,
    )

    main_drainage_info_dict = {}
    for _, row in main_df.iterrows():
        main_info = get_main_drainage_info(
            row = row,
            y_location_df = y_location_df,
            main_detail_df = main_detail_df,
            yobikei_gaikei_df = yobikei_gaikei_df,
        )
        main_drainage_info_dict[(main_info.bridge_name, main_info.drainage_name)] = main_info

    road_drainage_info_dict = {}
    mid = []
    for _, row in road_df.iterrows():
        if not pd.isna(row["つなぎ_始点"]):
            mid.append(row)
            continue
        road_info = get_road_drainage_info(
            row = row,
            y_location_df = y_location_df,
            road_detail_df = road_detail_df,
            yobikei_gaikei_df = yobikei_gaikei_df,
            main_drainage_info_dict = main_drainage_info_dict,
            road_drainage_info_dict = None,
        ) # まずはつなぎ以外
        road_drainage_info_dict[(road_info.bridge_name, road_info.drainage_name)] = road_info
    for row in mid:
        road_info = get_road_drainage_info(
            row = row,
            y_location_df = y_location_df,
            road_detail_df = road_detail_df,
            yobikei_gaikei_df = yobikei_gaikei_df,
            main_drainage_info_dict = main_drainage_info_dict,
            road_drainage_info_dict = road_drainage_info_dict,
        )
        road_drainage_info_dict[(road_info.bridge_name, road_info.drainage_name)] = road_info

    substructure_drainage_info_dict = {}
    for _, row in substructure_df.iterrows():
        substructure_info = get_substructure_drainage_info(
            row = row,
            y_location_df = y_location_df,
            substructure_detail_df = substructure_detail_df,
            yobikei_gaikei_df = yobikei_gaikei_df,
            main_drainage_info_dict = main_drainage_info_dict,
            road_drainage_info_dict = road_drainage_info_dict,
        )
        substructure_drainage_info_dict[(substructure_info.bridge_name, substructure_info.drainage_name)] = substructure_info

    save_json_and_pickle(
        data = main_drainage_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.MAIN}",
    )
    save_json_and_pickle(
        data = road_drainage_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.ROAD}",
    )
    save_json_and_pickle(
        data = substructure_drainage_info_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.SUBSTRUCTURE}",
    )
    save_json_and_pickle(
        data = target_point_name_dict,
        folder_path = output_dir,
        name = f"{Filenames.INPUT}_{Filenames.DRAINAGE}_{Filenames.POINTS}",
    )

if __name__ == "__main__":
    main("initial")
