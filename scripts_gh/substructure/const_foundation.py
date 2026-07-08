from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd
import Rhino.Geometry as rg

from my_project.config.paths import get_output_dir
from my_project.config.util_schemas import LocalOffset, Point2D, Point3D, Vector2D
from my_project.utils.geometry.vectors import normalize
from my_project.utils.geometry_gh.attributes import (
    sort_points_clockwise_from_upper_right,
)
from my_project.utils.geometry_gh.const import (
    const_extrude_brep_from_curve,
    const_point_obj,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle



def get_each_footing(
    ref_point: Point3D,
    ref_offset: LocalOffset,
    corner_points: list[Point3D],
    height: float,
) -> tuple[rg.Brep, float, list[Point3D]]:
    corner_points_2D = sort_points_clockwise_from_upper_right(
        points = corner_points,
        center = ref_point
    )
    top_z = ref_point.z + ref_offset.z #基準点からマイナス、を足す（負値）
    top_corner_points = [Point3D(p.X, p.Y, top_z) for p in corner_points_2D]
    corner_points_3D = [const_point_obj(p) for p in top_corner_points]
    footing_polyline = rg.Polyline(corner_points_3D + [corner_points_3D[0]])
    footing_curve = rg.PolylineCurve(footing_polyline)
    footing_brep = const_extrude_brep_from_curve(
        crv = footing_curve,
        vector = rg.Vector3d(0, 0, -height),
        cap=True,
    )
    return footing_brep, top_z - height, top_corner_points

def get_each_piles(
    ref_point: Point3D,
    corner_points: list[Point3D],
    top_z: float,
    depth_per_x: list[float],
    diameter: float,
    number_of_piles: int,
    x_num: int,
    y_num: int,
) -> list[rg.Brep]:
    corner_points_2D = sort_points_clockwise_from_upper_right(
        points = corner_points,
        center = ref_point
    )
    zero_point = corner_points_2D[2] # 第三象限の点をゼロ点とする
    x_vec = normalize(Vector2D(corner_points_2D[1].X - corner_points_2D[2].X, corner_points_2D[1].Y - corner_points_2D[2].Y)) 
    y_vec = normalize(Vector2D(corner_points_2D[3].X - corner_points_2D[2].X, corner_points_2D[3].Y - corner_points_2D[2].Y))
    x_vec = rg.Vector2d(x_vec.x, x_vec.y)
    y_vec = rg.Vector2d(y_vec.x, y_vec.y)
    X_len = corner_points_2D[1].DistanceTo(corner_points_2D[2])
    Y_len = corner_points_2D[3].DistanceTo(corner_points_2D[2])
    # 外周だけのパターンと全体に配置するパターンがある。
    piles = []
    if number_of_piles == x_num * y_num:
        pos_type = "full"
    else:
        pos_type = "edge"

    for i in range(x_num):
        for j in range(y_num):
            if pos_type == "edge" and i not in [0, x_num-1] and j not in [0, y_num-1]:
                continue
            pile_center = Point3D(
                zero_point.X + x_vec.X * X_len / (x_num - 1) * i + y_vec.X * Y_len / (y_num - 1) * j,
                zero_point.Y + x_vec.Y * X_len / (x_num - 1) * i + y_vec.Y * Y_len / (y_num - 1) * j,
                top_z,
            )
            pile_height = depth_per_x[i]
            circle = rg.Circle(const_point_obj(pile_center), diameter/2)
            pile_brep = const_extrude_brep_from_curve(
                crv = circle,
                vector = rg.Vector3d(0, 0, -pile_height),
                cap=True,
            )
            piles.append(pile_brep)
    return piles
                
def get_caisson(
    centers: list[Point2D],
    ref_point: Point3D,
    ref_offset: LocalOffset,
    diameter: float,
    depth: float,
) -> list[rg.Brep]:
    caissons = []
    for center in centers:
        center_3D = Point3D(center.x, center.y, ref_point.z + ref_offset.z)
        caisson_circle = rg.Circle(const_point_obj(center_3D), diameter/2)
        caisson_brep = const_extrude_brep_from_curve(
            crv = caisson_circle,
            vector = rg.Vector3d(0, 0, -depth),
            cap=True,
        )
        caissons.append(caisson_brep)
    return caissons
    
def main(initial_or_final: str):
    DIR = get_output_dir(initial_or_final)

    pier_indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.PIER}_{Filenames.INDIV}.pickle")
    abut_indiv_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ABUT}_{Filenames.INDIV}.pickle")
    indiv_infos = {**pier_indiv_infos, **abut_indiv_infos}
    world_foundation_dict_for_bake = {}
    abut_footing_top_points_dict = {}

    for substructure_name, indiv_info in indiv_infos.items():
        if pd.isna(indiv_info.footing) and pd.isna(indiv_info.caisson):
            print(f"{substructure_name}の基礎はありません")
            continue
        elif not pd.isna(indiv_info.footing):
            footing, height, footing_top_points = get_each_footing(
                ref_point = indiv_info.footing.reference_point,
                ref_offset = indiv_info.footing.reference_offset,
                corner_points = indiv_info.footing.corner_points,
                height = indiv_info.footing.height,
            )
            world_foundation_dict_for_bake[f"{substructure_name}_フーチング"] = footing
            if substructure_name in abut_indiv_infos:
                abut_footing_top_points_dict[substructure_name] = footing_top_points
            piles = get_each_piles(
                ref_point = indiv_info.footing.reference_point,
                corner_points = indiv_info.piles.corner_points,
                top_z = height,
                depth_per_x = indiv_info.piles.depths_by_x,
                diameter = indiv_info.piles.diameter,
                number_of_piles = int(indiv_info.piles.number_of_piles),
                x_num = int(indiv_info.piles.count_x),
                y_num = int(indiv_info.piles.count_y),
            )
            for i, pile in enumerate(piles):
                world_foundation_dict_for_bake[f"{substructure_name}_場所打ち杭_{i+1}"] = pile
        elif not pd.isna(indiv_info.caisson):
            caissons = get_caisson(
                centers = indiv_info.caisson.centers,
                ref_point = indiv_info.caisson.reference_point,
                ref_offset = indiv_info.caisson.reference_offset,
                diameter = indiv_info.caisson.diameter,
                depth = indiv_info.caisson.depth,
            )
            for i, caisson in enumerate(caissons):
                world_foundation_dict_for_bake[f"{substructure_name}_深礎_{i+1}"] = caisson

    save_json_and_pickle(
        data=abut_footing_top_points_dict,
        folder_path=DIR,
        name=f"{Filenames.WORLD}_{Filenames.ABUT}_{Filenames.FOOTING}_{Filenames.TOP}_{Filenames.POINTS}",
    )

    items = world_foundation_dict_for_bake.items()
    keys = [k for k, _ in items]
    values = [v for _, v in items]

    return keys, values
        

if __name__ == "__main__":
    bake_keys, bake_objs = main("initial")
