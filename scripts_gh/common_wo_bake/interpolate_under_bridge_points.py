# ruff: noqa: E402

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.util_schemas import Point3D
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def interpolate_sections(source_data: dict) -> list[dict]:
    def interpolate_value(start: float, end: float, ratio: float) -> float:
        return start + (end - start) * ratio

    def get_side_plane(item: dict, section: dict) -> tuple[Point3D, Point3D]:
        side = str(item["side"])
        if "左" in side or "上り" in side:
            return section["up_side_point"], section["up_side_normal"]
        if "右" in side or "下り" in side:
            return section["down_side_point"], section["down_side_normal"]
        raise ValueError(
            f'Cannot select side road CL for point: {item["key"]}; side={side}'
        )

    def get_signed_offset(item: dict, section: dict) -> float:
        point = item["point"]
        reference_point, normal = get_side_plane(item, section)
        delta_x = point.x - reference_point.x
        delta_y = point.y - reference_point.y
        return delta_x * normal.x + delta_y * normal.y

    def interpolate_target(target: dict, source_sections: dict[str, dict]) -> dict:
        start_section = source_sections[target["start_label"]]
        end_section = source_sections[target["end_label"]]
        ratio = target["ratio"]
        end_items = {item["key"]: item for item in end_section["items"]}
        items = []
        for start_item in start_section["items"]:
            end_item = end_items.get(start_item["key"])
            if end_item is None:
                continue
            start_offset = get_signed_offset(start_item, start_section)
            end_offset = get_signed_offset(end_item, end_section)
            offset = interpolate_value(start_offset, end_offset, ratio)
            reference_point, normal = get_side_plane(start_item, target)
            items.append(
                {
                    "name": start_item["name"],
                    "key": start_item["key"],
                    "type": start_item["type"],
                    "side": start_item["side"],
                    "source_x": interpolate_value(
                        start_item["source_x"],
                        end_item["source_x"],
                        ratio,
                    ),
                    "offset_from_side_CL": offset,
                    "point": Point3D(
                        x=reference_point.x + normal.x * offset,
                        y=reference_point.y + normal.y * offset,
                        z=interpolate_value(
                            start_item["point"].z,
                            end_item["point"].z,
                            ratio,
                        ),
                    ),
                }
            )
        return {
            **target,
            "items": items,
        }

    source_sections = {
        label: {"label": label, **section}
        for label, section in source_data["sections"].items()
    }
    sections = list(source_sections.values())
    sections.extend(
        interpolate_target(target, source_sections)
        for target in source_data["interpolation_targets"]
    )
    return sorted(sections, key=lambda section: section["center_distance"])


def main(initial_or_final: str = "initial", debug: bool = False):
    output_dir = get_output_dir(initial_or_final)
    source_name = (
        f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}"
        "_under_bridge_source"
    )
    source_data = load_from_pickle(output_dir / f"{source_name}.pickle")
    sections = interpolate_sections(source_data)
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
    result = {
        "sections": sections_dict,
        "points": point_dict,
    }
    save_json_and_pickle(
        data=result,
        folder_path=output_dir,
        name=f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}_under_bridge",
    )
    bake_keys, bake_objs = get_keys_and_values_for_bake(point_dict)
    if debug:
        points = [
            item["point"]
            for section in sections
            for item in section["items"]
        ]
        return bake_keys, bake_objs, point_dict, points
    return bake_keys, bake_objs


if __name__ == "__main__":
    bake_keys, bake_objs = main(
        globals().get("initial_or_final", "initial"),
        debug=False,
    )
