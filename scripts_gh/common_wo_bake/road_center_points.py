import math

import Rhino.Geometry as rg

from my_project.config.constants import (
    CENTERLINE_POLYLINE_SEGMENT_LENGTH,
    DISTANCE_TOL,
    EPS,
)
from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time
from my_project.config.paths import (
    FINAL_OUTPUT_DIR,
    INITIAL_OUTPUT_DIR,
)
from my_project.config.schemas.road_center_schemas import (
    RoadCenterInfo,
    typeInfo,
)
from my_project.utils.geometry_gh.attributes import get_point_on_crv_at_distance
from my_project.utils.geometry_gh.const import (
    const_3Dpoint,
    const_arc_from_p0_p1_radius,
    const_point_obj,
)
from my_project.utils.geometry_gh.transform import (
    transform_local_points_with_p0_and_angle,
)
from my_project.utils.io import load_from_pickle, save_json_and_pickle

normalize_lc_time()


def get_end_tangent_of_curve(crv):
    t_end = crv.Domain.T1
    tangent = crv.TangentAt(t_end)
    tangent.Unitize()
    return tangent

def get_points_along_arc(start_point: rg.Point3d, end_point: rg.Point3d, type_info: typeInfo) -> tuple[list[rg.Point3d], list[float], rg.Vector3d]:
    p0 = const_point_obj(start_point)
    p1 = const_point_obj(end_point)
    R = abs(float(type_info.radius))
    arc = const_arc_from_p0_p1_radius(p0, p1, R, type_info.direction)
    length = arc.GetLength()
    distances = [0.0]
    d = CENTERLINE_POLYLINE_SEGMENT_LENGTH
    while d < length:
        distances.append(d)
        d += CENTERLINE_POLYLINE_SEGMENT_LENGTH
    if length - distances[-1] > DISTANCE_TOL:
        distances.append(length)
    points_on_arc = [get_point_on_crv_at_distance(arc, d) for d in distances]
    end_tangent = get_end_tangent_of_curve(arc)
    return points_on_arc, distances, end_tangent

def local_clothoid_points_by_step(k0, k1, L):
    if L <= 0:
        raise ValueError("L must be positive")
    q = (k1 - k0) / L
    x = 0.0
    y = 0.0
    pts = [rg.Point3d(x, y, 0.0)]
    distances = [0.0]
    s = 0.0
    while s < L:
        step = min(CENTERLINE_POLYLINE_SEGMENT_LENGTH, L - s)
        s_mid = s + 0.5 * step
        theta = k0 * s_mid + 0.5 * q * s_mid * s_mid
        x += step * math.cos(theta)
        y += step * math.sin(theta)
        s += step
        distances.append(s)
        pts.append(rg.Point3d(x, y, 0.0))
    return pts, distances

def curvature_from_radius(radius, direction):
    if radius == float("inf"):
        return 0.0
    r = abs(float(radius))
    if direction == "left":
        sign = -1.0
    elif direction == "right":
        sign = 1.0
    else:
        raise ValueError(f"Invalid curve direction: {direction}")
    return sign / r


def get_chord_tangent(start_point: rg.Point3d, end_point: rg.Point3d) -> rg.Vector3d:
    tangent = rg.Vector3d(
        end_point.X - start_point.X,
        end_point.Y - start_point.Y,
        0.0,
    )
    if not tangent.Unitize():
        raise ValueError(f"Start and end points are too close: {start_point}, {end_point}")
    return tangent


def append_segment_points(
    all_points: list[rg.Point3d],
    all_STAs: list[float],
    segment_points: list[rg.Point3d],
    segment_STAs: list[float],
) -> None:
    if len(segment_points) != len(segment_STAs):
        raise ValueError(
            f"points and STAs length mismatch: points={len(segment_points)}, STAs={len(segment_STAs)}"
        )
    start_idx = 1 if all_points else 0
    all_points.extend(segment_points[start_idx:])
    all_STAs.extend(segment_STAs[start_idx:])


def make_clothoid_from_endpoints_radii(
    start_point: rg.Point3d,
    end_point: rg.Point3d,
    start_STA: float,
    end_STA: float,
    start_tangent: rg.Vector3d,
    type_info: typeInfo,
):
    p0 = const_point_obj(start_point)
    p1 = const_point_obj(end_point)
    k0 = curvature_from_radius(type_info.start_radius, type_info.direction)
    k1 = curvature_from_radius(type_info.end_radius, type_info.direction)

    dk = k1 - k0

    if abs(dk) < 1e-12:
        raise ValueError("R0とR1の曲率が同じです。クロソイドではなく、直線または円弧です。")
    L = end_STA - start_STA

    # Aは結果として計算
    A = math.sqrt(L / abs(dk))

    local_pts, distances = local_clothoid_points_by_step(k0, k1, L)
    tangent = rg.Vector3d(start_tangent)
    rot_angle = math.atan2(tangent.Y, tangent.X)

    world_pts = [transform_local_points_with_p0_and_angle(local_pt, p0, rot_angle) for local_pt in local_pts]

    # 念のため最後の点を厳密にp1へ合わせる
    world_pts[-1] = p1

    print("clothoid length L =", L)
    print("A =", A)
    print("k0 =", k0)
    print("k1 =", k1)
    print("points =", len(world_pts))

    theta_end = rot_angle + 0.5 * (k0 + k1) * L
    end_tangent = rg.Vector3d(
        math.cos(theta_end),
        math.sin(theta_end),
        0.0
    )
    end_tangent.Unitize()
    return world_pts, distances, end_tangent

def get_indiv_center_line_points(
    road_center_info: RoadCenterInfo,
    debug=False,
) -> list[rg.Point3d]:
    plan_key_points = road_center_info.plan_Coord_infos
    plan_key_points = [const_point_obj(p) for p in plan_key_points]
    plan_key_points_STAs = road_center_info.plan_STAs
    type_infos = road_center_info.type_infos
    center_line_points_2D = []
    center_line_points_2D_STAs = []
    current_tangent = None
    for i in range(len(plan_key_points)-1):
        start_point = plan_key_points[i]
        end_point = plan_key_points[i+1]
        start_STA = plan_key_points_STAs[i]
        end_STA = plan_key_points_STAs[i+1]
        type_info = type_infos[i]
        if type_info.type == "line":
            this_center_line_points_2D = [start_point, end_point]
            this_center_line_points_2D_STAs = [start_STA, end_STA]
            current_tangent = get_chord_tangent(start_point, end_point)
            if debug:
                this_center_line_points_2D = []
                this_center_line_points_2D_STAs = []
        elif type_info.type == "arc":
            this_center_line_points_2D, distances, current_tangent = get_points_along_arc(start_point, end_point, type_info)
            this_center_line_points_2D_STAs = [start_STA + distance for distance in distances]
            if debug:
                this_center_line_points_2D = []
                this_center_line_points_2D_STAs = []
        elif type_info.type == "clothoid":
            if current_tangent is None:
                current_tangent = get_chord_tangent(start_point, end_point)
            this_center_line_points_2D, distances, end_tangent = make_clothoid_from_endpoints_radii(
                start_point=start_point,
                end_point=end_point,
                start_STA=start_STA,
                end_STA=end_STA,
                start_tangent=current_tangent,
                type_info=type_info,
            )
            current_tangent = end_tangent
            this_center_line_points_2D_STAs = [start_STA + distance for distance in distances]
        else:
            raise ValueError(f"Unsupported road center segment type: {type_info.type}")

        append_segment_points(
            center_line_points_2D,
            center_line_points_2D_STAs,
            this_center_line_points_2D,
            this_center_line_points_2D_STAs,
        )
    z_infos = sorted(road_center_info.z_infos, key=lambda z_info: z_info.STA)
    zs = [z_info.z for z_info in z_infos]
    z_STAs = [z_info.STA for z_info in z_infos]
    z_pre_slopes = [z_info.pre_slope for z_info in z_infos]
    z_post_slopes = [z_info.post_slope for z_info in z_infos]
    center_line_points = []
    for pt_2D, STA in zip(center_line_points_2D, center_line_points_2D_STAs):
        if STA <= z_STAs[0]:
            z = zs[0] + z_pre_slopes[0] * (z_STAs[0] - STA)
        elif STA >= z_STAs[-1]:
            z = zs[-1] + z_post_slopes[-1] * (STA - z_STAs[-1])
        else:
            for i in range(len(z_STAs)-1):
                if z_STAs[i] <= STA <= z_STAs[i+1]:
                    if abs(z_post_slopes[i]) < EPS:
                        z = zs[i]
                    else:
                        z = zs[i] + z_post_slopes[i] * (STA - z_STAs[i])
                    break
        center_line_points.append(rg.Point3d(pt_2D.X, pt_2D.Y, z))
    return center_line_points
    

def main(initial_or_final: str, debug=False):
    if initial_or_final == "initial":
        DIR = INITIAL_OUTPUT_DIR
    elif initial_or_final == "final":
        DIR = FINAL_OUTPUT_DIR

    road_center_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ROAD_CENTER}.pickle")
    center_line_points_dict = {}
    if debug:
        points  = []
        for name, road_center_infos in road_center_infos.items():
            print(name)
            center_line_points = get_indiv_center_line_points(
                road_center_info = road_center_infos,
                debug=debug,
            )
            points.extend(center_line_points)
    else:
        points  = []
        for name, road_center_infos in road_center_infos.items():
            print(name)
            center_line_points = get_indiv_center_line_points(
                road_center_info = road_center_infos,
                debug=debug,
            )
            points.extend(center_line_points)
            center_line_points_dict[name] = [const_3Dpoint(pt) for pt in center_line_points] # シリアライズのために変換
        save_json_and_pickle(
            data = center_line_points_dict,
            folder_path = DIR,
            name = f"{Filenames.ROAD_CENTER}_{Filenames.POINTS}",
        )
    return points





if __name__ == "__main__":
    points = main("initial")
    # points = main("initial", debug=True)
