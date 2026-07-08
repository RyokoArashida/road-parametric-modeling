
from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import math

import Rhino.Geometry as rg

from my_project.config.file_names import Filenames
from my_project.config.paths import get_output_dir
from my_project.config.schemas.wall_schemas import (
    RefPointInfo,
    WallInfo,
)
from my_project.config.util_schemas import (
    Point2D,
    Point3D,
    Vector2D,
)
from my_project.utils.dataframe import flatten_any
from my_project.utils.geometry.points import (
    get_point_by_xy_offset_with_z_delta,
    get_point_by_z_offset_on_line,
)
from my_project.utils.geometry_gh.attributes import (
    get_distance_along_crv,
    get_point_on_crv_at_distance,
)
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_closed_polycurve_obj,
    const_point_obj,
    const_polycurve_obj,
    const_srf_from_2crvs,
    join_breps_or_raise,
)
from my_project.utils.geometry_gh.document import get_named_points_on_layer
from my_project.utils.io import load_from_pickle, save_json_and_pickle


def make_top_bottom_points_num_same(
    top_points2D: list[Point2D],
    bottom_points2D: list[Point2D],
    top_gap_point_num: list[int],
    bottom_gap_point_num: list[int],
    ref_points: list[RefPointInfo]
) -> tuple[list[Point2D], list[Point2D]]:
    top_match_point_num = [i for i in range(len(top_points2D)) if i not in top_gap_point_num]
    bottom_match_point_num = [i for i in range(len(bottom_points2D)) if i not in bottom_gap_point_num]
    if len(top_match_point_num) != len(bottom_match_point_num):
        raise ValueError(
            f"top_match_point_numとbottom_match_point_numの長さが一致しません。"
            f"top_match_point_num: {top_match_point_num}, bottom_match_point_num: {bottom_match_point_num}"
        )
    top_polyline = const_polycurve_obj(top_points2D)
    bottom_polyline = const_polycurve_obj(bottom_points2D)
    top_distances = get_distance_along_crv(top_polyline,top_points2D)
    bottom_distances = get_distance_along_crv(bottom_polyline,bottom_points2D)

    ref_top_distances = []
    ref_bottom_distances = []
    for ref_point in ref_points:
        top_num = int(ref_point.top_num)
        bottom_num = int(ref_point.bottom_num)
        top_ref_distance = top_distances[top_num]
        bottom_ref_distance = bottom_distances[bottom_num]
        ref_top_distances.append(top_ref_distance)
        ref_bottom_distances.append(bottom_ref_distance)


    full_top_points2D = []
    full_top_points2D_distances = []
    full_bottom_points2D = []
    full_bottom_points2D_distances = []
    for i in range(len(top_match_point_num) - 1):
        top_match_start_num = top_match_point_num[i]
        top_match_end_num = top_match_point_num[i + 1]
        bottom_match_start_num = bottom_match_point_num[i]
        bottom_match_end_num = bottom_match_point_num[i + 1]
        full_top_points2D.append(top_points2D[top_match_start_num])
        full_top_points2D_distances.append(top_distances[top_match_start_num])
        full_bottom_points2D.append(bottom_points2D[bottom_match_start_num])
        full_bottom_points2D_distances.append(bottom_distances[bottom_match_start_num])
        if top_match_end_num - top_match_start_num > 1:
            top_match_start_distance = top_distances[top_match_start_num]
            top_match_end_distance = top_distances[top_match_end_num]
            bottom_match_start_distance = bottom_distances[bottom_match_start_num]
            bottom_match_end_distance = bottom_distances[bottom_match_end_num]
            for j in range(top_match_start_num + 1, top_match_end_num):
                full_top_points2D.append(top_points2D[j])
                full_top_points2D_distances.append(top_distances[j])
                ratio = (top_distances[j] - top_match_start_distance) / (top_match_end_distance - top_match_start_distance)
                bottom_distance = bottom_match_start_distance + ratio * (bottom_match_end_distance - bottom_match_start_distance)
                bottom_point = get_point_on_crv_at_distance(bottom_polyline, bottom_distance)
                full_bottom_points2D.append(Point2D(x=bottom_point.X, y=bottom_point.Y))
                full_bottom_points2D_distances.append(bottom_distance)
            for j in range(bottom_match_start_num + 1, bottom_match_end_num):
                full_bottom_points2D.append(bottom_points2D[j])
                full_bottom_points2D_distances.append(bottom_distances[j])
                ratio = (bottom_distances[j] - bottom_match_start_distance) / (bottom_match_end_distance - bottom_match_start_distance)
                top_distance = top_match_start_distance + ratio * (top_match_end_distance - top_match_start_distance)
                top_point = get_point_on_crv_at_distance(top_polyline, top_distance)
                full_top_points2D.append(Point2D(x=top_point.X, y=top_point.Y))
                full_top_points2D_distances.append(top_distance)
    full_top_points2D.append(top_points2D[top_match_point_num[-1]])
    full_top_points2D_distances.append(top_distances[top_match_point_num[-1]])
    full_bottom_points2D.append(bottom_points2D[bottom_match_point_num[-1]])
    full_bottom_points2D_distances.append(bottom_distances[bottom_match_point_num[-1]])
    # distancesの昇順でソートする
    full_top_points2D, full_top_points2D_distances = zip(*sorted(zip(full_top_points2D, full_top_points2D_distances), key=lambda x: x[1]))
    full_bottom_points2D, full_bottom_points2D_distances = zip(*sorted(zip(full_bottom_points2D, full_bottom_points2D_distances), key=lambda x: x[1]))

    top_ref_point_idx = [i for i, pt in enumerate(full_top_points2D) if full_top_points2D_distances[i] in ref_top_distances]
    top_original_point_idx = [i for i, pt in enumerate(full_top_points2D) if full_top_points2D_distances[i] in top_distances]
    bottom_ref_point_idx = [i for i, pt in enumerate(full_bottom_points2D) if full_bottom_points2D_distances[i] in ref_bottom_distances]
    return (
        list(full_top_points2D),
        list(full_bottom_points2D),
        list(top_ref_point_idx),
        list(bottom_ref_point_idx),
        list(full_top_points2D_distances),
        list(full_bottom_points2D_distances),
        list(top_original_point_idx),
    )

def get_top_xy_offset_from_slope_offset(
    offset: float,
    slope: float,
) -> float:
    return offset * math.sqrt(1 + slope ** 2)

def get_bottom_xy_z_offset_from_slope_offset(
    offset: float,
    slope: float,
) -> tuple[float, float]:
    offset_xy = offset / math.sqrt(1 + slope ** 2)
    offset_z = offset_xy * slope
    return offset_xy, offset_z

def get_z_from_ref_points(
    point_idx: int,
    ref_point_idx: list[int],
    distances: list[float],
    ref_zs: list[float],
) -> float:
    if point_idx in ref_point_idx:
        return ref_zs[ref_point_idx.index(point_idx)]
    for j in range(len(ref_point_idx) - 1):
        if ref_point_idx[j] < point_idx < ref_point_idx[j + 1]:
            prev_idx = ref_point_idx[j]
            next_idx = ref_point_idx[j + 1]
            ratio = (distances[point_idx] - distances[prev_idx]) / (distances[next_idx] - distances[prev_idx])
            return ref_zs[j] + ratio * (ref_zs[j + 1] - ref_zs[j])
    raise ValueError(f"Failed to interpolate wall point z: point_idx={point_idx}, ref_point_idx={ref_point_idx}")

def cap_planar_holes_or_raise(
    brep: rg.Brep,
    context: str,
    tol: float = 0.01,
) -> rg.Brep:
    capped = brep.CapPlanarHoles(tol)
    if capped is None:
        raise ValueError(f"Failed to cap planar holes ({context})")
    return capped

def get_indiv_points(
    wall_info: WallInfo,
    top_points2D: list[Point2D],
    bottom_points2D: list[Point2D],
    berm_points2D: list[Point2D],
) -> tuple[list[Point3D], list[Point3D], list[Point3D], list[Vector2D]]:
    (
        full_top_points2D,
        full_bottom_points2D,
        top_ref_point_idx,
        bottom_ref_point_idx,
        full_top_points2D_distances,
        full_bottom_points2D_distances,
        top_original_point_idx,
    ) = make_top_bottom_points_num_same(
        top_points2D=top_points2D,
        bottom_points2D=bottom_points2D,
        top_gap_point_num=wall_info.top_gap_point_num,
        bottom_gap_point_num=wall_info.bottom_gap_point_num,
        ref_points=wall_info.reference_points
    )
    top_points3D = []
    bottom_points3D = []
    embed_points3D = []
    berm_points3D = []

    embed_depth = wall_info.block_info.embed_depth
    top_ref_zs = [ref_point.top_z for ref_point in wall_info.reference_points]
    bottom_ref_zs = [ref_point.bottom_z for ref_point in wall_info.reference_points]

    for i in range(len(full_top_points2D)):
        top_point_2D = full_top_points2D[i]
        bottom_point_2D = full_bottom_points2D[i]

        top_z = get_z_from_ref_points(
            point_idx=i,
            ref_point_idx=top_ref_point_idx,
            distances=full_top_points2D_distances,
            ref_zs=top_ref_zs,
        )
        bottom_z = get_z_from_ref_points(
            point_idx=i,
            ref_point_idx=bottom_ref_point_idx,
            distances=full_bottom_points2D_distances,
            ref_zs=bottom_ref_zs,
        )
        top_point3D = Point3D(x=top_point_2D.x, y=top_point_2D.y, z=top_z)
        bottom_point3D = Point3D(x=bottom_point_2D.x, y=bottom_point_2D.y, z=bottom_z)
        top_points3D.append(top_point3D)
        bottom_points3D.append(bottom_point3D)
        embed_point3D = get_point_by_z_offset_on_line(
            point1=bottom_point3D,
            point2=top_point3D,
            offset_z=-embed_depth,
        )
        embed_points3D.append(embed_point3D)

    berm_gap_point_num = wall_info.berm_gap_point_num
    berm_polyline = const_polycurve_obj(berm_points2D)
    berm_points_distances = get_distance_along_crv(berm_polyline, berm_points2D)
    match_berm_points2D = [berm_points2D[i] for i in range(len(berm_points2D)) if i not in berm_gap_point_num]
    if len(match_berm_points2D) != len(top_original_point_idx):
        raise ValueError(
            f"match_berm_points2Dとtop_original_point_idxの長さが一致しません。"
            f"match_berm_points2D: {match_berm_points2D}, top_original_point_idx: {top_original_point_idx}"
        )
    for i, berm_point_2D in enumerate(match_berm_points2D):
        if berm_point_2D in match_berm_points2D:
            idx = match_berm_points2D.index(berm_point_2D)
            top_point3D = top_points3D[top_original_point_idx[idx]]
            berm_point3D = Point3D(x=berm_point_2D.x, y=berm_point_2D.y, z=top_point3D.z)
        else:
            prev_ref_idx = max([j for j in range(len(match_berm_points2D)) if j < i])
            next_ref_idx = min([j for j in range(len(match_berm_points2D)) if j > i])
            prev_z = top_points3D[top_original_point_idx[prev_ref_idx]].Z
            next_z= top_points3D[top_original_point_idx[next_ref_idx]].Z
            prev_berm_idx = berm_points2D.index(match_berm_points2D[prev_ref_idx])
            next_berm_idx = berm_points2D.index(match_berm_points2D[next_ref_idx])
            prev_berm_distance = berm_points_distances[prev_berm_idx]
            next_berm_distance = berm_points_distances[next_berm_idx]
            this_berm_distance = berm_points_distances[i]
            ratio = (this_berm_distance - prev_berm_distance) / (next_berm_distance - prev_berm_distance)
            berm_z = prev_z + ratio * (next_z - prev_z)
            berm_point3D = Point3D(x=berm_point_2D.x, y=berm_point_2D.y, z=berm_z)
        berm_points3D.append(berm_point3D)
    return top_points3D, bottom_points3D, embed_points3D, berm_points3D

def get_indiv_wall(
    wall_info: WallInfo,
    top_points2D: list[Point2D],
    bottom_points2D: list[Point2D],
    berm_points2D: list[Point2D],
) -> tuple[dict[str, rg.Brep], list[Point3D], list[Point3D]]:
    top_points3D, bottom_points3D, embed_points3D, berm_points3D = get_indiv_points(
        wall_info=wall_info,
        top_points2D=top_points2D,
        bottom_points2D=bottom_points2D,
        berm_points2D=berm_points2D,
    )
    block_polylines = [] #表上、表下、裏下、裏上
    backfill_concrete_polylines = []
    backfill_stone_polylines = []
    base_polylines = [] # ブロック表下、表上、表下、裏下、裏上

    front_slope = wall_info.block_info.front_slope.value
    block_top_offset_xy = get_top_xy_offset_from_slope_offset(
        offset=wall_info.block_info.block_width,
        slope=front_slope,
    )
    block_bottom_offset_xy, block_bottom_offset_z = get_bottom_xy_z_offset_from_slope_offset(
        offset=wall_info.block_info.block_width,
        slope=front_slope,
    )
    fill_con_top_offset_xy = get_top_xy_offset_from_slope_offset(
        offset=wall_info.block_info.backfill_concrete_width,
        slope=front_slope,
    )
    fill_con_bottom_offset_xy, fill_con_bottom_offset_z = get_bottom_xy_z_offset_from_slope_offset(
        offset=wall_info.block_info.backfill_concrete_width,
        slope=front_slope,
    )
    fill_stone_offset_xy_top = get_top_xy_offset_from_slope_offset(
        offset=wall_info.block_info.backfill_stone_top_width,
        slope=front_slope,
    )

    for top_point, bottom_point, embed_point in zip(top_points3D, bottom_points3D, embed_points3D):
        block_front_top = top_point
        block_front_bottom = embed_point
        block_back_top = get_point_by_xy_offset_with_z_delta(
            point1=block_front_top,
            point2=block_front_bottom,
            offset_xy=-1 * block_top_offset_xy,
            offset_z=0,
        )
        block_back_bottom = get_point_by_xy_offset_with_z_delta(
            point1=block_front_bottom,
            point2=block_front_top,
            offset_xy=block_bottom_offset_xy,
            offset_z=-1 * block_bottom_offset_z,
        )
        block_polylines.append(const_closed_polycurve_obj([block_front_top, block_front_bottom, block_back_bottom, block_back_top]))


        fill_con_front_top = block_back_top
        fill_con_front_bottom = block_back_bottom
        fill_con_back_top = get_point_by_xy_offset_with_z_delta(
            point1=fill_con_front_top,
            point2=fill_con_front_bottom,
            offset_xy=-1 * fill_con_top_offset_xy,
            offset_z=0,
        )
        fill_con_back_bottom = get_point_by_xy_offset_with_z_delta(
            point1=fill_con_front_bottom,
            point2=fill_con_front_top,
            offset_xy=fill_con_bottom_offset_xy,
            offset_z=-1 * fill_con_bottom_offset_z,
        )
        backfill_concrete_polylines.append(const_closed_polycurve_obj([fill_con_front_top, fill_con_front_bottom, fill_con_back_bottom, fill_con_back_top]))

        fill_stone_offset_xy_bottom = fill_stone_offset_xy_top + (top_point.z - bottom_point.z) * (wall_info.block_info.front_slope.value - wall_info.block_info.back_slope.value)
        fill_stone_front_top = fill_con_back_top
        fill_stone_front_bottom = get_point_by_z_offset_on_line(
            point1=fill_con_back_top,
            point2=fill_con_back_bottom,
            offset_z=bottom_point.z - fill_con_back_top.z,
        )
        fill_stone_back_top = get_point_by_xy_offset_with_z_delta(
            point1=fill_stone_front_top,
            point2=fill_stone_front_bottom,
            offset_xy=-1 * fill_stone_offset_xy_top,
            offset_z=0,
        )
        fill_stone_back_bottom = get_point_by_xy_offset_with_z_delta(
            point1=fill_stone_front_bottom,
            point2=fill_stone_front_top,
            offset_xy=fill_stone_offset_xy_bottom,
            offset_z=0,
        )
        backfill_stone_polylines.append(const_closed_polycurve_obj([fill_stone_front_top, fill_stone_front_bottom, fill_stone_back_bottom, fill_stone_back_top]))

        base_embed = block_front_bottom
        base_back_top = fill_con_back_bottom
        base_front_top = get_point_by_xy_offset_with_z_delta(
            point1 = base_embed,
            point2 = top_point,
            offset_xy = -1 * wall_info.block_info.foundation_front_offset,
            offset_z = 0,
        )
        base_front_bottom = Point3D(x=base_front_top.x, y=base_front_top.y, z=base_front_top.z - wall_info.block_info.foundation_front_height)
        base_back_bottom = Point3D(x=base_back_top.x, y=base_back_top.y, z=base_front_bottom.z)
        base_polylines.append(const_closed_polycurve_obj([base_embed, base_front_top, base_front_bottom, base_back_bottom, base_back_top]))
    
    block_breps = [const_srf_from_2crvs([block_polylines[i], block_polylines[i + 1]]) for i in range(len(block_polylines) - 1)]
    backfill_concrete_breps = [const_srf_from_2crvs([backfill_concrete_polylines[i], backfill_concrete_polylines[i + 1]]) for i in range(len(backfill_concrete_polylines) - 1)]
    backfill_stone_breps = [const_srf_from_2crvs([backfill_stone_polylines[i], backfill_stone_polylines[i + 1]]) for i in range(len(backfill_stone_polylines) - 1)]
    base_breps = [const_srf_from_2crvs([base_polylines[i], base_polylines[i + 1]]) for i in range(len(base_polylines) - 1)]
    block_brep = cap_planar_holes_or_raise(
        join_breps_or_raise(block_breps, context="wall block"),
        context="wall block",
    )
    backfill_concrete_brep = cap_planar_holes_or_raise(
        join_breps_or_raise(backfill_concrete_breps, context="wall backfill concrete"),
        context="wall backfill concrete",
    )
    backfill_stone_brep = cap_planar_holes_or_raise(
        join_breps_or_raise(backfill_stone_breps, context="wall backfill stone"),
        context="wall backfill stone",
    )
    base_brep = cap_planar_holes_or_raise(
        join_breps_or_raise(base_breps, context="wall base"),
        context="wall base",
    )
    wall_brep_dict = {
        "block": block_brep,
        "backfill_concrete": backfill_concrete_brep,
        "backfill_stone": backfill_stone_brep,
        "base": base_brep
    }
    return wall_brep_dict, top_points3D, bottom_points3D, berm_points3D


def get_ordered_wall_points(
    numbered_points: list[tuple[int, rg.Point3d]],
    required_point_nums: list[int],
    context: str,
) -> list[Point2D]:
    nums = [num for num, _ in numbered_points]
    duplicate_nums = sorted({num for num in nums if nums.count(num) > 1})
    if duplicate_nums:
        raise ValueError(f"{context} の点番号が重複しています。duplicates={duplicate_nums}")
    point_by_num = {num: pt for num, pt in numbered_points}
    found_nums = sorted(point_by_num.keys())
    if found_nums:
        expected_nums = list(range(found_nums[0], found_nums[-1] + 1))
        if found_nums != expected_nums:
            raise ValueError(
                f"{context} の点番号が連続していません。"
                f"expected={expected_nums}, found={found_nums}"
            )
    missing_nums = [num for num in required_point_nums if num not in point_by_num]
    if missing_nums:
        raise ValueError(
            f"{context} の点が不足しています。"
            f"missing={missing_nums}, found={found_nums}"
        )
    return [
        Point2D(x=point_by_num[num].X, y=point_by_num[num].Y)
        for num in sorted(point_by_num.keys())
    ]


def main(initial_or_final: str, debug: bool = False) -> tuple[list[str], list[rg.Brep]]:
    DIR = get_output_dir(initial_or_final)

    wall_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.WALL}.pickle")

    wall_points2D = get_named_points_on_layer(layer_index) # layer_indexはGrasshopperから直接入力する
    print(wall_points2D)

    wall_points_dict = {}
    world_items_dict_for_bake = {}
    world_items_dict_for_bake_2 = {}
    world_items_dict_for_bake_3 = {}

    for wall_info in wall_infos:
        fullname = f"{wall_info.location}_{wall_info.name}"
        top_points2D = [
            (int(key.replace(f"{fullname}_上_", "")), pt)
            for key, pt in wall_points2D.items()
            if key.startswith(f"{fullname}_上_")
        ]
        bottom_points2D = [
            (int(key.replace(f"{fullname}_下_", "")), pt)
            for key, pt in wall_points2D.items()
            if key.startswith(f"{fullname}_下_")
        ]
        berm_points2D = [
            (int(key.replace(f"{fullname}_小段_", "")), pt)
            for key, pt in wall_points2D.items()
            if key.startswith(f"{fullname}_小段_")
        ]
        required_top_nums = sorted({
            int(ref_point.top_num) for ref_point in wall_info.reference_points
        } | set(wall_info.top_gap_point_num))
        required_bottom_nums = sorted({
            int(ref_point.bottom_num) for ref_point in wall_info.reference_points
        } | set(wall_info.bottom_gap_point_num))
        top_points2D = get_ordered_wall_points(
            top_points2D,
            required_top_nums,
            context=f"{fullname}_上",
        )
        bottom_points2D = get_ordered_wall_points(
            bottom_points2D,
            required_bottom_nums,
            context=f"{fullname}_下",
        )
        berm_points2D = get_ordered_wall_points(
            berm_points2D,
            [num for num, _ in berm_points2D],
            context=f"{fullname}_小段",
        )
        wall_brep_dict, top_points3D, bottom_points3D, berm_points3D = get_indiv_wall(wall_info, top_points2D, bottom_points2D, berm_points2D)
        for i, pt in enumerate(top_points3D):
            wall_points_dict[f"{fullname}_上_{i}"] = const_3Dpoint(pt)
        for i, pt in enumerate(bottom_points3D):
            wall_points_dict[f"{fullname}_下_{i}"] = const_3Dpoint(pt)
        for i, pt in enumerate(berm_points3D):
            wall_points_dict[f"{fullname}_小段_{i}"] = const_3Dpoint(pt)
        
        world_items_dict_for_bake[fullname] = wall_brep_dict
    
    save_json_and_pickle(
        data = wall_points_dict,
        folder_path = DIR,
        name = f"{Filenames.WORLD}_{Filenames.WALL}_{Filenames.POINTS}",
    )
    def get_keys_and_values_for_bake(world_items_dict):
        flatten_dict_for_bake = flatten_any(world_items_dict)
        items = list(flatten_dict_for_bake.items())
        # valueがNoneのものはbakeできないので除外
        items = [(k,v) for k,v in items if v is not None]
        keys = [k for k, _ in items]
        values = [v for _, v in items]
        return keys, values
    
    if not debug:
        return get_keys_and_values_for_bake(world_items_dict_for_bake)
    if debug:
        points = [const_point_obj(pt) for pt in top_points3D + bottom_points3D + berm_points3D]
        return get_keys_and_values_for_bake(world_items_dict_for_bake), points
    



if __name__ == "__main__":
    # (bake_keys, bake_objs) = main("initial")
    (bake_keys, bake_objs), points = main("initial", debug=True)
