# ruff: noqa: E402

from typing import Optional

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.constants import DEFAULT_GEOMETRY_EXTENT
from my_project.config.file_names import Filenames
from my_project.config.paths import get_input_output_dirs, get_output_dir
from my_project.config.util_schemas import Point3D
from my_project.utils.coordinates import get_STA_from_STA_info
from my_project.utils.geometry.points import get_distance_3D
from my_project.utils.geometry_gh.const import const_3Dpoint, const_polycurve_obj
from my_project.utils.geometry_gh.intersect import get_intersections_with_vertical_plane
from my_project.utils.geometry_gh.road_surface import (
    get_center_sample_at_STA,
    get_indiv_center_line_points,
)
from my_project.utils.io import load_from_pickle, read_file_to_df, save_json_and_pickle

DEFAULT_CROSS_SECTION_FILE_NAME = "本線横断点.csv"


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
        "up": ["up", "上", "左"],
        "down": ["down", "下", "右"],
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
    return {
        "points": points,
        "left_vectors": left_vectors,
        "STAs": STAs,
        "curve": const_polycurve_obj([const_3Dpoint(point) for point in points]),
    }


def make_center_line_items(road_center_infos: dict) -> dict[str, dict]:
    return {
        name: make_center_line_item(road_center_info)
        for name, road_center_info in road_center_infos.items()
    }


def make_orthogonal_line_points(
    center_point: rg.Point3d,
    left_vector,
    half_length: float = DEFAULT_GEOMETRY_EXTENT,
) -> tuple[Point3D, Point3D]:
    return (
        Point3D(
            x=center_point.X - left_vector.x * half_length,
            y=center_point.Y - left_vector.y * half_length,
            z=center_point.Z,
        ),
        Point3D(
            x=center_point.X + left_vector.x * half_length,
            y=center_point.Y + left_vector.y * half_length,
            z=center_point.Z,
        ),
    )


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
            "Side road center line and orthogonal STA line do not intersect. "
            f"anchor_point={anchor_point}"
        )
    nearest_point = min(
        intersection_points,
        key=lambda point: get_distance_3D(point, anchor_point),
    )
    return Point3D(nearest_point.x, nearest_point.y, anchor_point.z)


def point_on_z0(point) -> Point3D:
    point = const_3Dpoint(point)
    return Point3D(point.x, point.y, 0.0)


def get_group_STA(group_df) -> float:
    first_row = group_df.iloc[0]
    return get_STA_from_STA_info(first_row["STA大"], first_row["STA小"])


def get_side_road_intersections_at_STA(
    center_line_items: dict[str, dict],
    target_STA: float,
    center_name: str,
    up_side_name: str,
    down_side_name: str,
) -> dict:
    center_item = center_line_items[center_name]
    center_point, left_vector, _ = get_center_sample_at_STA(
        target_STA=target_STA,
        center_line_points=center_item["points"],
        left_vectors=center_item["left_vectors"],
        center_line_STAs=center_item["STAs"],
    )
    anchor_point = const_3Dpoint(center_point)
    orthogonal_line_points = make_orthogonal_line_points(
        center_point=center_point,
        left_vector=left_vector,
    )

    up_point = get_nearest_intersection(
        center_line_items[up_side_name]["curve"],
        orthogonal_line_points,
        anchor_point,
    )
    down_point = get_nearest_intersection(
        center_line_items[down_side_name]["curve"],
        orthogonal_line_points,
        anchor_point,
    )

    return {
        "target_STA": target_STA,
        "center_name": center_name,
        "up_side_name": up_side_name,
        "down_side_name": down_side_name,
        "center_point": anchor_point,
        "orthogonal_line_points": orthogonal_line_points,
        "up_side_point": up_point,
        "down_side_point": down_point,
    }


def const_indiv_points(
    group_df,
    center_line_items: dict[str, dict],
    center_name: str,
    up_side_name: str,
    down_side_name: str,
) -> list[Point3D]:
    target_STA = get_group_STA(group_df)
    try:
        result = get_side_road_intersections_at_STA(
            center_line_items=center_line_items,
            target_STA=target_STA,
            center_name=center_name,
            up_side_name=up_side_name,
            down_side_name=down_side_name,
        )
    except ValueError as exc:
        if "out of center line range" in str(exc):
            print(f"Skip under bridge STA outside center line range: {target_STA}")
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
    points = []
    for _, group_df in cross_section_df.groupby(["STA大", "STA小"], sort=False):
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
        return points

    result = {"points": points}
    save_json_and_pickle(
        data=result,
        folder_path=DIR,
        name=f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}_under_bridge",
    )
    return result


if __name__ == "__main__":
    points = main(
        globals().get("initial_or_final", "initial"),
        debug=True,
    )
