# 今のところ橋台で区切られる土工部しか扱っていない。


from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()



from typing import Optional

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo
from my_project.config.schemas.embankment_schemas import (
    CrossSectionInfo,
    EdgePoints,
    EdgeStructureInfo,
    LocalTopBottomPointInfo,
)
from my_project.config.schemas.wall_schemas import (
    RefPointInfo,
)
from my_project.config.util_schemas import (
    Point3D,
)
from my_project.utils.bake import get_keys_and_values_for_bake
from my_project.utils.geometry.points import (
    get_point_by_xy_offset_with_z_delta,
    transform_local_point_by_corresponding_points,
    transform_local_point_to_world_vertical_plane,
)
from my_project.utils.geometry_gh.attributes import (
    get_point_on_crv_at_distance,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_brep_from_all_crvs,
    const_point_obj,
    const_polycurve_obj,
)
from my_project.utils.geometry_gh.intersect import (
    split_brep_by_vertical_srf_from_two_points_keep_near_point,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

def get_indiv_brep(points):
    


def main(initial_or_final: str, debug: bool = False):
    DIR = get_output_dir(initial_or_final)
    embankment_points = load_from_pickle(
        file_path=DIR / f"{Filenames.INPUT}_{Filenames.WORLD}_{Filenames.EMBANKMENT}_{Filenames.POINTS}.pickle",
    )

    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    world_items_dict_for_bake_3 = {}

    for name, emb_points in embankment_points:
        embankment_brep = get_indiv_brep(
            points = emb_points
        )

        world_items_dict_for_bake[name] = embankment_brep

    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)
    if debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)




if __name__ == "__main__":
    (bake_keys, bake_objs) = main("initial", debug=True)
