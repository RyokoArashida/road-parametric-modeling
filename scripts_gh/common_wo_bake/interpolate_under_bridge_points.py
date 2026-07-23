# ruff: noqa: E402

import Rhino.Geometry as rg

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

    def get_horizontal_direction(section: dict) -> rg.Vector3d:
        up_point = section["up_side_point"]
        down_point = section["down_side_point"]
        direction = rg.Vector3d(
            down_point.x - up_point.x,
            down_point.y - up_point.y,
            0.0,
        )
        if not direction.Unitize():
            raise ValueError(
                f'Side road CL points coincide: {section["label"]}'
            )
        return direction

    def get_signed_offset(item: dict, section: dict, direction: rg.Vector3d) -> float:
        point = item["point"]
        center_point = section["center_point"]
        return (
            (point.x - center_point.x) * direction.X
            + (point.y - center_point.y) * direction.Y
        )

    def interpolate_target(target: dict, source_sections: dict[str, dict]) -> dict:
        start_section = source_sections[target["start_label"]]
        end_section = source_sections[target["end_label"]]
        ratio = target["ratio"]
        target_direction = get_horizontal_direction(target)
        start_direction = get_horizontal_direction(start_section)
        end_direction = get_horizontal_direction(end_section)
        end_items = {item["key"]: item for item in end_section["items"]}
        items = []
        for start_item in start_section["items"]:
            end_item = end_items.get(start_item["key"])
            if end_item is None:
                continue
            start_offset = get_signed_offset(
                start_item,
                start_section,
                start_direction,
            )
            end_offset = get_signed_offset(
                end_item,
                end_section,
                end_direction,
            )
            offset = interpolate_value(start_offset, end_offset, ratio)
            center_point = target["center_point"]
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
                    "offset_from_center": offset,
                    "point": Point3D(
                        x=center_point.x + target_direction.X * offset,
                        y=center_point.y + target_direction.Y * offset,
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
            "items": sorted(
                items,
                key=lambda item: item["offset_from_center"],
            ),
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
