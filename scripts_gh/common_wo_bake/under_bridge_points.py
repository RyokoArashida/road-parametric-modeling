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
from my_project.utils.geometry_gh.attributes import get_curve_distance
from my_project.utils.geometry_gh.const import const_3Dpoint, const_polycurve_obj
from my_project.utils.geometry_gh.intersect import (
    get_intersect_point_on_crv_and_points_in_the_same_plane,
)
from my_project.utils.geometry_gh.road_surface import get_indiv_center_line_points
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle

DEFAULT_CROSS_SECTION_FILE_NAME = "側道横断点.csv"
MAIN_STA_BIG_COL = "本線STA大"
MAIN_STA_SMALL_COL = "本線STA小"
SIDE_STA_BIG_COL = "側道STA大"
SIDE_STA_SMALL_COL = "側道STA小"
X_COL = "X"
Y_COL = "Y"
HEIGHT_COL = "高さ"
SIDE_COL = "側"
POINT_NAME_COL = "点名"
POINT_TYPE_COL = "種別"
POINT_NO_COL = "点番号"
SECTION_DIVISION_COUNT = 20


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
    curve_z0 = const_polycurve_obj(
        [
            rg.Point3d(converted.x, converted.y, 0.0)
            for converted in (const_3Dpoint(point) for point in points)
        ]
    )
    return {
        "points": points,
        "left_vectors": left_vectors,
        "STAs": STAs,
        "curve": curve,
        "curve_z0": curve_z0,
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
        SIDE_COL,
        POINT_NAME_COL,
        POINT_NO_COL,
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
            f"Required columns are missing in {DEFAULT_CROSS_SECTION_FILE_NAME}. "
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


def get_point_key(row) -> str:
    side = str(row[SIDE_COL]).strip()
    name = str(row[POINT_NAME_COL])
    point_no = row[POINT_NO_COL]
    if is_missing(point_no):
        return name
    if side:
        return f"{side}{int(float(point_no))}"
    return f"{name}_{int(float(point_no))}"


def get_side_cl_rows(group_df):
    side_rows = group_df[group_df[POINT_TYPE_COL] == "側道CL"]
    up_rows = side_rows[
        side_rows[SIDE_COL].astype(str).str.contains("上り")
        | side_rows[POINT_NAME_COL].astype(str).str.contains("上り")
    ]
    down_rows = side_rows[
        side_rows[SIDE_COL].astype(str).str.contains("下り")
        | side_rows[POINT_NAME_COL].astype(str).str.contains("下り")
    ]
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
        side = str(row[SIDE_COL])
        point_key = get_point_key(row)
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
                "key": point_key,
                "type": point_type,
                "side": side,
                "source_x": source_x,
                "point": point,
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
    center_point = get_intersect_point_on_crv_and_points_in_the_same_plane(
        center_line_items[center_name]["curve_z0"],
        [
            Point3D(x=up_side_point.x, y=up_side_point.y, z=0.0),
            Point3D(x=down_side_point.x, y=down_side_point.y, z=0.0),
        ],
    )
    center_distance = get_curve_distance(
        center_line_items[center_name]["curve_z0"],
        center_point,
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
        "center_point": center_point,
        "center_distance": center_distance,
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
            or "out of center line length" in str(exc)
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
        "center_point": result["center_point"],
        "center_distance": result["center_distance"],
        "up_side_STA": result["up_side_STA"],
        "down_side_STA": result["down_side_STA"],
        "up_side_point": result["up_side_point"],
        "down_side_point": result["down_side_point"],
    }


def get_interpolation_targets(
    sections: list[dict],
    center_curve,
    up_side_center_line_item: dict,
    down_side_center_line_item: dict,
    division_count: int = SECTION_DIVISION_COUNT,
) -> list[dict]:
    def interpolate_value(start: float, end: float, ratio: float) -> float:
        return start + (end - start) * ratio

    def get_center_point_at_distance(distance: float) -> Point3D:
        ok, parameter = center_curve.LengthParameter(distance)
        if not ok:
            raise ValueError(
                f"Failed to get main center line point at distance: {distance}"
            )
        point = center_curve.PointAt(parameter)
        return Point3D(x=point.X, y=point.Y, z=0.0)

    def make_target(
        start_section: dict,
        end_section: dict,
        ratio: float,
    ) -> dict:
        start_distance = start_section["center_distance"]
        end_distance = end_section["center_distance"]
        center_distance = interpolate_value(
            start_distance,
            end_distance,
            ratio,
        )
        center_point = get_center_point_at_distance(center_distance)
        up_side_STA = interpolate_value(
            start_section["up_side_STA"],
            end_section["up_side_STA"],
            ratio,
        )
        down_side_STA = interpolate_value(
            start_section["down_side_STA"],
            end_section["down_side_STA"],
            ratio,
        )
        up_point_2D = get_center_line_point_at_distance(
            up_side_center_line_item,
            up_side_STA,
        )
        down_point_2D = get_center_line_point_at_distance(
            down_side_center_line_item,
            down_side_STA,
        )
        up_point = Point3D(
            x=up_point_2D.x,
            y=up_point_2D.y,
            z=interpolate_value(
                start_section["up_side_point"].z,
                end_section["up_side_point"].z,
                ratio,
            ),
        )
        down_point = Point3D(
            x=down_point_2D.x,
            y=down_point_2D.y,
            z=interpolate_value(
                start_section["down_side_point"].z,
                end_section["down_side_point"].z,
                ratio,
            ),
        )
        return {
            "STA": interpolate_value(
                start_section["STA"], end_section["STA"], ratio
            ),
            "label": f"interp_{center_distance:.3f}",
            "start_label": start_section["label"],
            "end_label": end_section["label"],
            "ratio": ratio,
            "center_point": center_point,
            "center_distance": center_distance,
            "up_side_STA": up_side_STA,
            "down_side_STA": down_side_STA,
            "up_side_point": up_point,
            "down_side_point": down_point,
        }

    if division_count < 2:
        raise ValueError(
            f"Section interpolation division count must be at least 2: {division_count}"
        )
    if len(sections) < 2:
        return []

    sections = sorted(sections, key=lambda section: section["center_distance"])
    targets = []
    for start_section, end_section in zip(sections[:-1], sections[1:]):
        start_distance = start_section["center_distance"]
        end_distance = end_section["center_distance"]
        if end_distance - start_distance <= DISTANCE_TOL:
            print(
                "Skip under bridge interpolation span with duplicate center distance: "
                f'{start_section["label"]} -> {end_section["label"]}'
            )
            continue
        for division_index in range(1, division_count):
            targets.append(
                make_target(
                    start_section,
                    end_section,
                    division_index / division_count,
                )
            )
    return targets


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

    sections = sorted(sections, key=lambda section: section["center_distance"])
    interpolation_targets = get_interpolation_targets(
        sections,
        center_line_items[center_name]["curve_z0"],
        center_line_items[up_side_name],
        center_line_items[down_side_name],
    )
    sections_dict = {
        section["label"]: {
            key: value for key, value in section.items() if key != "label"
        }
        for section in sections
    }
    point_dict = {
        section["label"]: {
            item["key"]: item["point"]
            for item in section["items"]
        }
        for section in sections
    }
    points = [
        point_to_rg(item["point"])
        for section in sections
        for item in section["items"]
    ]
    bake_keys, bake_objs = get_keys_and_values_for_bake(point_dict)
    reference_point_dict = {
        section["label"]: {
            "本線CL": section["center_point"],
            "側道上りCL": section["up_side_point"],
            "側道下りCL": section["down_side_point"],
        }
        for section in [*sections, *interpolation_targets]
    }
    bake_keys2, bake_objs2 = get_keys_and_values_for_bake(reference_point_dict)
    result = {
        "sections": sections_dict,
        "points": point_dict,
        "reference_points": reference_point_dict,
        "interpolation_targets": interpolation_targets,
    }
    save_json_and_pickle(
        data=result,
        folder_path=DIR,
        name=(
            f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}"
            "_under_bridge_source"
        ),
    )
    if debug:
        return (
            bake_keys,
            bake_objs,
            bake_keys2,
            bake_objs2,
            point_dict,
            points,
            crvs,
        )
    return bake_keys, bake_objs, bake_keys2, bake_objs2


if __name__ == "__main__":
    bake_keys, bake_objs, bake_keys2, bake_objs2 = main(
        globals().get("initial_or_final", "initial"),
        debug=False,
    )
