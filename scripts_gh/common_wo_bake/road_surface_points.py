# ruff: noqa: E402

from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time
from my_project.config.paths import get_output_dir
from my_project.utils.geometry_gh.const import const_3Dpoint
from my_project.utils.geometry_gh.road_surface import (
    get_embankment_edge_points,
    get_indiv_center_line_points,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

normalize_lc_time()


def main(initial_or_final: str, debug=False):
    DIR = get_output_dir(initial_or_final)

    road_center_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}.pickle")
    center_line_info_dict = {}
    edge_info_dict = {}
    if debug:
        points = []
        for name, road_center_info in road_center_infos.items():
            print(name)
            center_line_points, left_vectors, center_line_STAs = get_indiv_center_line_points(
                road_center_info=road_center_info,
            )
            points.extend(center_line_points)
            if road_center_info.embankment_pave_infos is not None:
                this_U_edge_points_dict, this_D_edge_points_dict, _ = get_embankment_edge_points(
                    center_line_points=center_line_points,
                    left_vectors=left_vectors,
                    center_line_STAs=center_line_STAs,
                    embankment_pave_infos=road_center_info.embankment_pave_infos,
                )
                for _, U_edge_points in this_U_edge_points_dict.items():
                    points.extend(U_edge_points)
                for _, D_edge_points in this_D_edge_points_dict.items():
                    points.extend(D_edge_points)
        return points

    for name, road_center_info in road_center_infos.items():
        print(name)
        center_line_points, left_vectors, center_line_STAs = get_indiv_center_line_points(
            road_center_info=road_center_info,
        )
        center_line_info_dict[name] = {
            "STAs": center_line_STAs,
            "points": [const_3Dpoint(pt) for pt in center_line_points],
        }
        if road_center_info.embankment_pave_infos is not None:
            this_U_edge_points_dict, this_D_edge_points_dict, this_edge_STAs_dict = get_embankment_edge_points(
                center_line_points=center_line_points,
                left_vectors=left_vectors,
                center_line_STAs=center_line_STAs,
                embankment_pave_infos=road_center_info.embankment_pave_infos,
            )
            for n in this_edge_STAs_dict.keys():
                edge_info_dict[f"{name}_{n}"] = {
                    "STAs": this_edge_STAs_dict[n],
                    "U_points": [const_3Dpoint(pt) for pt in this_U_edge_points_dict[n]],
                    "D_points": [const_3Dpoint(pt) for pt in this_D_edge_points_dict[n]],
                }
    save_json_and_pickle(
        data=center_line_info_dict,
        folder_path=DIR,
        name=f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}",
    )
    save_json_and_pickle(
        data=edge_info_dict,
        folder_path=DIR,
        name=f"{Filenames.ROAD}_{Filenames.EDGE}_{Filenames.POINTS}",
    )
    return None


if __name__ == "__main__":
    points = main("initial")
    # points = main("initial", debug=True)
