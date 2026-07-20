# ruff: noqa: E402

import Rhino.Geometry as rg

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry_gh.const import const_polycurve_obj, const_srf_from_2crvs
from my_project.utils.io import load_from_pickle

FOLD_POINT_TYPE = "その他折れ点"


def get_under_bridge_points_pickle_path(initial_or_final: str):
    output_dir = get_output_dir(initial_or_final)
    name = f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}_under_bridge"
    return output_dir / f"{name}.pickle"


def is_section_key_item(item: dict) -> bool:
    return item["type"] != FOLD_POINT_TYPE


def make_cross_section_curve(section: dict) -> rg.PolylineCurve:
    return const_polycurve_obj([item["point"] for item in section["items"]])


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
        curves[key] = const_polycurve_obj([item["point"] for item in part_items])
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


def load_sections(initial_or_final: str) -> list[dict]:
    data = load_from_pickle(get_under_bridge_points_pickle_path(initial_or_final))
    sections_dict = data["sections"]
    sections = [
        {
            "label": label,
            "STA": section["STA"],
            "items": section["items"],
        }
        for label, section in sections_dict.items()
    ]
    return sorted(sections, key=lambda section: section["STA"])


def main(
    initial_or_final: str = "initial",
    debug: bool = False,
):
    sections = load_sections(initial_or_final)
    section_crvs, srfs, srf_dict = make_surfaces_between_sections(sections)
    bake_key, bake_obj = get_keys_and_values_for_bake(srf_dict)

    if debug:
        return bake_key, bake_obj, section_crvs, srfs
    return bake_key, bake_obj


if __name__ == "__main__":
    bake_key, bake_obj = main(globals().get("initial_or_final", "initial"))
