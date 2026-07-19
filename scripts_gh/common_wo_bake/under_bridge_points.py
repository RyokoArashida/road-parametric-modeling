# ruff: noqa: E402

from typing import Optional

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.constants import DISTANCE_TOL
from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs, get_output_dir
from my_project.config.util_schemas import Point3D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.geometry.points import get_distance_3D
from my_project.utils.geometry_gh.const import const_3Dpoint, const_polycurve_obj
from my_project.utils.geometry_gh.intersect import get_intersections_with_vertical_plane
from my_project.utils.geometry_gh.road_surface import get_indiv_center_line_points
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle

DEFAULT_CROSS_SECTION_FILE_NAME = "本線横断点.csv"
MAIN_STA_BIG_COL = "本線STA大"
MAIN_STA_SMALL_COL = "本線STA小"
SIDE_STA_BIG_COL = "側道STA大"
SIDE_STA_SMALL_COL = "側道STA小"


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


def get_nearest_intersection(
    target_curve,
    cutter_line_points: tuple[Point3D, Point3D],
    anchor_point: Point3D,
) -> Point3D:
    intersection_points = get_intersections_with_vertical_plane(
        target_curve,
        cutter_line_points,
        z=anchor_point.z,
    )
    if not intersection_points:
        raise ValueError(
            "Target center line and cross section line do not intersect. "
            f"anchor_point={anchor_point}"
        )
    nearest_point = min(
        intersection_points,
        key=lambda point: get_distance_3D(point, anchor_point),
    )
    return Point3D(nearest_point.x, nearest_point.y, anchor_point.z)


def point_on_z0(point) -> rg.Point3d:
    point = const_3Dpoint(point)
    return rg.Point3d(point.x, point.y, 0.0)


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
        "種別",
        "点名",
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


def get_main_intersection_from_side_STAs(
    center_line_items: dict[str, dict],
    center_name: str,
    up_side_name: str,
    down_side_name: str,
    up_side_STA: float,
    down_side_STA: float,
) -> dict:
    up_side_point = get_center_line_point_at_distance(
        center_line_items[up_side_name],
        up_side_STA,
    )
    down_side_point = get_center_line_point_at_distance(
        center_line_items[down_side_name],
        down_side_STA,
    )
    anchor_point = Point3D(
        x=(up_side_point.x + down_side_point.x) / 2,
        y=(up_side_point.y + down_side_point.y) / 2,
        z=(up_side_point.z + down_side_point.z) / 2,
    )

    center_point = get_nearest_intersection(
        center_line_items[center_name]["curve"],
        (up_side_point, down_side_point),
        anchor_point,
    )

    return {
        "center_name": center_name,
        "up_side_name": up_side_name,
        "down_side_name": down_side_name,
        "up_side_STA": up_side_STA,
        "down_side_STA": down_side_STA,
        "center_point": center_point,
        "cross_section_line_points": (up_side_point, down_side_point),
        "up_side_point": up_side_point,
        "down_side_point": down_side_point,
    }


def const_indiv_points(
    group_df,
    center_line_items: dict[str, dict],
    center_name: str,
    up_side_name: str,
    down_side_name: str,
) -> list[rg.Point3d]:
    group_label = get_group_label(group_df)
    try:
        up_side_row, down_side_row = get_side_cl_rows(group_df)
        up_side_STA = get_optional_STA_from_row(up_side_row)
        down_side_STA = get_optional_STA_from_row(down_side_row)
        if up_side_STA is None or down_side_STA is None:
            raise ValueError("Side road STA is missing.")
        result = get_main_intersection_from_side_STAs(
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
            or "上り and 下り 側道CL rows are required" in str(exc)
            or "Side road STA is missing" in str(exc)
        ):
            print(f"Skip under bridge group: {group_label}; {exc}")
            return []
        raise
    return [
        point_on_z0(result["center_point"]),
        point_on_z0(result["up_side_point"]),
        point_on_z0(result["down_side_point"]),
    ]


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
    points = []
    for _, group_df in cross_section_df.groupby(
        [MAIN_STA_BIG_COL, MAIN_STA_SMALL_COL],
        sort=False,
    ):
        points.extend(
            const_indiv_points(
                group_df=group_df,
                center_line_items=center_line_items,
                center_name=center_name,
                up_side_name=up_side_name,
                down_side_name=down_side_name,
            )
        )

    if debug:
        return points, crvs

    result = {"points": points, "crvs": crvs}
    save_json_and_pickle(
        data=result,
        folder_path=DIR,
        name=f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}_under_bridge",
    )
    return result


if __name__ == "__main__":
    points, crvs = main(
        globals().get("initial_or_final", "initial"),
        debug=True,
    )
