# ruff: noqa: E402

from typing import Optional

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.constants import DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs, get_output_dir
from my_project.config.util_schemas import Point3D
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_polycurve_obj,
    const_srf_from_2crvs,
)
from my_project.utils.geometry_gh.road_surface import get_indiv_center_line_points
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle

DEFAULT_CROSS_SECTION_FILE_NAME = "本線横断点.csv"
MAIN_STA_BIG_COL = "本線STA大"
MAIN_STA_SMALL_COL = "本線STA小"
SIDE_STA_BIG_COL = "側道STA大"
SIDE_STA_SMALL_COL = "側道STA小"
X_COL = "X"
Y_COL = "Y"
HEIGHT_COL = "高さ"
POINT_NAME_COL = "点名"
POINT_TYPE_COL = "種別"
FOLD_POINT_TYPE = "その他折れ点"


def get_available_center_names(road_center_infos: dict) -> list[str]:
    return sorted(str(name) for name in road_center_infos.keys())


def find_name_by_keywords(names: list[str], keywords: list[str]) -> Optional[str]:
    for name in names:
        lower_name = name.lower()
        if all(keyword.lower() in lower_name for keyword in keywords):
            return name
    return None


def infer_center_name(names: list[str]) -> str:
    main_name = find_name_by_keywords(names, ["main"])
    if main_name is not None:
        return main_name

    non_side_names = [
        name
        for name in names
        if "side" not in name.lower()
        and "road" not in name.lower()
        and "ramp" not in name.lower()
    ]
    if len(non_side_names) == 1:
        return non_side_names[0]

    raise ValueError(
        "center_name could not be inferred. "
        f"Available center names: {names}"
    )


def infer_side_name(names: list[str], side: str) -> str:
    side_keywords = {
        "up": ["up", "上り"],
        "down": ["down", "下り"],
    }
    candidates = [
        [side, "side"],
        [side, "road"],
        [side],
    ]
    candidates.extend([[keyword] for keyword in side_keywords.get(side, [])])
    for keywords in candidates:
        name = find_name_by_keywords(names, keywords)
        if name is not None:
            return name

    raise ValueError(
        f"{side}_side_name could not be inferred. "
        f"Available center names: {names}"
    )


def make_center_line_item(road_center_info) -> dict:
    points, left_vectors, STAs = get_indiv_center_line_points(
        road_center_info=road_center_info,
    )
    curve = const_polycurve_obj([const_3Dpoint(point) for point in points])
    return {
        "points": points,
        "left_vectors": left_vectors,
        "STAs": STAs,
        "curve": curve,
        "length": curve.GetLength(),
    }


def make_center_line_items(road_center_infos: dict) -> dict[str, dict]:
    return {
        name: make_center_line_item(road_center_info)
        for name, road_center_info in road_center_infos.items()
    }


def point_to_rg(point) -> rg.Point3d:
    point = const_3Dpoint(point)
    return rg.Point3d(point.x, point.y, point.z)


def is_missing(value) -> bool:
    if value is None:
        return True
    if value != value:
        return True
    return str(value).strip() == ""


def get_group_label(group_df) -> str:
    first_row = group_df.iloc[0]
    return f'{first_row[MAIN_STA_BIG_COL]}+{first_row[MAIN_STA_SMALL_COL]}'


def validate_cross_section_columns(cross_section_df) -> None:
    required_cols = [
        MAIN_STA_BIG_COL,
        MAIN_STA_SMALL_COL,
        POINT_TYPE_COL,
        POINT_NAME_COL,
        X_COL,
        Y_COL,
        HEIGHT_COL,
        SIDE_STA_BIG_COL,
        SIDE_STA_SMALL_COL,
    ]
    missing_cols = [
        col for col in required_cols if col not in cross_section_df.columns
    ]
    if missing_cols:
        raise ValueError(
            "Required columns are missing in 本線横断点.csv. "
            f"missing={missing_cols}, columns={list(cross_section_df.columns)}"
        )


def get_optional_STA_from_row(row):
    sta_big = row[SIDE_STA_BIG_COL]
    sta_small = row[SIDE_STA_SMALL_COL]
    if is_missing(sta_big) or is_missing(sta_small):
        return None
    return get_STA_from_STA_info(sta_big, sta_small)


def get_required_float(row, col: str) -> float:
    value = row[col]
    if is_missing(value):
        raise ValueError(f"Required value is missing: {col}")
    return float(value)


def get_side_cl_rows(group_df):
    side_rows = group_df[group_df["種別"] == "側道CL"]
    up_rows = side_rows[side_rows["点名"].astype(str).str.contains("上り")]
    down_rows = side_rows[side_rows["点名"].astype(str).str.contains("下り")]
    if len(up_rows) < 1 or len(down_rows) < 1:
        raise ValueError("上り and 下り 側道CL rows are required.")
    return up_rows.iloc[0], down_rows.iloc[0]


def get_center_line_point_at_distance(
    center_line_item: dict,
    target_distance: float,
) -> Point3D:
    curve = center_line_item["curve"]
    curve_length = center_line_item["length"]
    if target_distance < -DISTANCE_TOL or target_distance > curve_length + DISTANCE_TOL:
        raise ValueError(
            f"Target side road STA {target_distance} is out of center line length: "
            f"0 to {curve_length}"
        )
    ok, parameter = curve.LengthParameter(
        min(max(target_distance, 0.0), curve_length)
    )
    if not ok:
        raise ValueError(
            f"Failed to get center line point by distance: {target_distance}"
        )
    center_point = curve.PointAt(parameter)
    return const_3Dpoint(center_point)


def get_side_road_point_with_height(
    center_line_item: dict,
    target_distance: float,
    row,
) -> Point3D:
    point = get_center_line_point_at_distance(center_line_item, target_distance)
    height = get_required_float(row, HEIGHT_COL) * 1000
    return Point3D(x=point.x, y=point.y, z=height)


def transform_section_point_to_vertical_plane(
    row,
    source_up_side_row,
    source_down_side_row,
    up_side_point: Point3D,
    down_side_point: Point3D,
) -> Point3D:
    source_x = get_required_float(row, X_COL)
    source_y = get_required_float(row, Y_COL)
    source_up_x = get_required_float(source_up_side_row, X_COL)
    source_up_y = get_required_float(source_up_side_row, Y_COL)
    source_down_x = get_required_float(source_down_side_row, X_COL)
    source_down_y = get_required_float(source_down_side_row, Y_COL)
    source_width = source_down_x - source_up_x
    source_height_diff = source_down_y - source_up_y
    if abs(source_width) <= DISTANCE_TOL:
        raise ValueError("Source side road CL X coordinates are the same.")
    if abs(source_height_diff) <= DISTANCE_TOL:
        raise ValueError("Source side road CL Y coordinates are the same.")

    horizontal_vector = rg.Vector3d(
        down_side_point.x - up_side_point.x,
        down_side_point.y - up_side_point.y,
        0.0,
    )
    horizontal_distance = horizontal_vector.Length
    if not horizontal_vector.Unitize():
        raise ValueError("Side road CL points have the same XY coordinates.")
    target_height_diff = down_side_point.z - up_side_point.z
    horizontal_offset = (
        (source_x - source_up_x) / source_width * horizontal_distance
    )
    vertical_offset = (
        (source_y - source_up_y) / source_height_diff * target_height_diff
    )

    return Point3D(
        x=up_side_point.x + horizontal_vector.X * horizontal_offset,
        y=up_side_point.y + horizontal_vector.Y * horizontal_offset,
        z=up_side_point.z + vertical_offset,
    )


def transform_section_items_to_vertical_plane(
    group_df,
    up_side_row,
    down_side_row,
    up_side_point: Point3D,
    down_side_point: Point3D,
) -> list[dict]:
    items = []
    for idx, row in group_df.iterrows():
        if is_missing(row[X_COL]) or is_missing(row[Y_COL]):
            continue
        name = str(row[POINT_NAME_COL])
        point_type = str(row[POINT_TYPE_COL])
        source_x = get_required_float(row, X_COL)
        if idx == up_side_row.name:
            point = up_side_point
        elif idx == down_side_row.name:
            point = down_side_point
        else:
            point = transform_section_point_to_vertical_plane(
                row,
                up_side_row,
                down_side_row,
                up_side_point,
                down_side_point,
            )
        items.append(
            {
                "name": name,
                "type": point_type,
                "source_x": source_x,
                "point": point,
                "rg_point": point_to_rg(point),
            }
        )
    return sorted(items, key=lambda item: item["source_x"])


def get_main_intersection_from_side_STAs(
    group_df,
    up_side_row,
    down_side_row,
    center_line_items: dict[str, dict],
    center_name: str,
    up_side_name: str,
    down_side_name: str,
    up_side_STA: float,
    down_side_STA: float,
) -> dict:
    up_side_point = get_side_road_point_with_height(
        center_line_items[up_side_name],
        up_side_STA,
        up_side_row,
    )
    down_side_point = get_side_road_point_with_height(
        center_line_items[down_side_name],
        down_side_STA,
        down_side_row,
    )
    section_items = transform_section_items_to_vertical_plane(
        group_df,
        up_side_row,
        down_side_row,
        up_side_point,
        down_side_point,
    )

    return {
        "center_name": center_name,
        "up_side_name": up_side_name,
        "down_side_name": down_side_name,
        "up_side_STA": up_side_STA,
        "down_side_STA": down_side_STA,
        "cross_section_line_points": (up_side_point, down_side_point),
        "up_side_point": up_side_point,
        "down_side_point": down_side_point,
        "section_items": section_items,
    }


def const_indiv_section(
    group_df,
    center_line_items: dict[str, dict],
    center_name: str,
    up_side_name: str,
    down_side_name: str,
) -> Optional[dict]:
    group_label = get_group_label(group_df)
    try:
        up_side_row, down_side_row = get_side_cl_rows(group_df)
        up_side_STA = get_optional_STA_from_row(up_side_row)
        down_side_STA = get_optional_STA_from_row(down_side_row)
        if up_side_STA is None or down_side_STA is None:
            raise ValueError("Side road STA is missing.")
        result = get_main_intersection_from_side_STAs(
            group_df=group_df,
            up_side_row=up_side_row,
            down_side_row=down_side_row,
            center_line_items=center_line_items,
            center_name=center_name,
            up_side_name=up_side_name,
            down_side_name=down_side_name,
            up_side_STA=up_side_STA,
            down_side_STA=down_side_STA,
        )
    except ValueError as exc:
        if (
            "out of center line range" in str(exc)
            or "do not intersect" in str(exc)
            or "交差が見つかりません" in str(exc)
            or "交点が見つかりません" in str(exc)
            or "上り and 下り 側道CL rows are required" in str(exc)
            or "Side road STA is missing" in str(exc)
            or "Required value is missing" in str(exc)
            or "Source side road CL" in str(exc)
        ):
            print(f"Skip under bridge group: {group_label}; {exc}")
            return None
        raise
    first_row = group_df.iloc[0]
    return {
        "STA": get_STA_from_STA_info(
            first_row[MAIN_STA_BIG_COL],
            first_row[MAIN_STA_SMALL_COL],
        ),
        "label": group_label,
        "items": result["section_items"],
    }


def make_cross_section_curve(section: dict) -> rg.PolylineCurve:
    return const_polycurve_obj([item["rg_point"] for item in section["items"]])


def is_section_key_item(item: dict) -> bool:
    return item["type"] != FOLD_POINT_TYPE


def make_section_part_curves(section: dict) -> dict[tuple[str, str], rg.PolylineCurve]:
    curves: dict[tuple[str, str], rg.PolylineCurve] = {}
    items = section["items"]
    key_indices = [
        idx for idx, item in enumerate(items)
        if is_section_key_item(item)
    ]
    for start_idx, end_idx in zip(key_indices[:-1], key_indices[1:]):
        start_item = items[start_idx]
        end_item = items[end_idx]
        key = (start_item["name"], end_item["name"])
        part_items = items[start_idx:end_idx + 1]
        curves[key] = const_polycurve_obj(
            [item["rg_point"] for item in part_items]
        )
    return curves


def make_surfaces_between_sections(
    sections: list[dict],
) -> tuple[list[rg.PolylineCurve], list[rg.Brep], dict]:
    section_crvs = [make_cross_section_curve(section) for section in sections]
    srfs = []
    srf_dict = {}
    prev_part_curves = None
    prev_section = None
    for section in sections:
        part_curves = make_section_part_curves(section)
        if prev_part_curves is not None:
            span_key = f'{prev_section["label"]}-{section["label"]}'
            srf_dict[span_key] = {}
            for key, curve in part_curves.items():
                prev_curve = prev_part_curves.get(key)
                if prev_curve is None:
                    continue
                srf = const_srf_from_2crvs([prev_curve, curve])
                srfs.append(srf)
                srf_dict[span_key][f"{key[0]}__{key[1]}"] = srf
        prev_part_curves = part_curves
        prev_section = section
    return section_crvs, srfs, srf_dict


def main(
    initial_or_final: str = "initial",
    debug: bool = False,
):
    input_dir, _ = get_input_output_dirs(initial_or_final)
    DIR = get_output_dir(initial_or_final)

    center_name = "本線"
    up_side_name = "側道上り"
    down_side_name = "側道下り"
    cross_section_csv_path = input_dir / DEFAULT_CROSS_SECTION_FILE_NAME

    cross_section_df = read_file_to_df(cross_section_csv_path)
    road_center_infos = load_from_pickle(
        DIR / f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}.pickle"
    )
    available_names = get_available_center_names(road_center_infos)
    if center_name is None:
        center_name = infer_center_name(available_names)
    if up_side_name is None:
        up_side_name = infer_side_name(available_names, "up")
    if down_side_name is None:
        down_side_name = infer_side_name(available_names, "down")

    center_line_items = make_center_line_items(road_center_infos)
    crvs = [
        center_line_items[center_name]["curve"],
        center_line_items[up_side_name]["curve"],
        center_line_items[down_side_name]["curve"],
    ]
    validate_cross_section_columns(cross_section_df)
    sections = []
    for _, group_df in cross_section_df.groupby(
        [MAIN_STA_BIG_COL, MAIN_STA_SMALL_COL],
        sort=False,
    ):
        section = const_indiv_section(
            group_df=group_df,
            center_line_items=center_line_items,
            center_name=center_name,
            up_side_name=up_side_name,
            down_side_name=down_side_name,
        )
        if section is not None:
            sections.append(section)

    sections = sorted(sections, key=lambda section: section["STA"])
    points = [
        item["rg_point"]
        for section in sections
        for item in section["items"]
    ]
    section_crvs, srfs, srf_dict = make_surfaces_between_sections(sections)
    bake_key, bake_obj = get_keys_and_values_for_bake(srf_dict)

    if debug:
        return points, crvs, section_crvs, srfs, bake_key, bake_obj

    result = {
        "points": points,
        "crvs": crvs,
        "section_crvs": section_crvs,
        "srfs": srfs,
        "bake_key": bake_key,
        "bake_obj": bake_obj,
    }
    save_json_and_pickle(
        data=result,
        folder_path=DIR,
        name=f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}_under_bridge",
    )
    return result


if __name__ == "__main__":
    points, crvs, section_crvs, srfs, bake_key, bake_obj = main(
        globals().get("initial_or_final", "initial"),
        debug=True,
    )
