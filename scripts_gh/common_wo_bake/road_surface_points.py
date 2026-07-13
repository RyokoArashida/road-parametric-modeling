# ruff: noqa: E402
import math

import Rhino.Geometry as rg

from my_project.config.constants import (
    CENTERLINE_POLYLINE_SEGMENT_LENGTH,
    DISTANCE_TOL,
    EPS,
)
from my_project.config.file_names import Filenames
from my_project.config.locale_compat import normalize_lc_time
from my_project.config.paths import get_output_dir
from my_project.config.schemas.road_surface_schemas import (
    EmbankmentPaveInfo,
    RoadSurfaceInfo,
    typeInfo,
)
from my_project.config.util_schemas import Vector2D
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

def get_unitized_tangent(crv, distance: float) -> rg.Vector3d:
    length = crv.GetLength()
    if distance <= 0:
        t = crv.Domain.T0
    elif distance >= length:
        t = crv.Domain.T1
    else:
        ok, t = crv.LengthParameter(distance)
        if not ok:
            raise ValueError(f"Failed to get curve parameter at distance {distance}")
    tangent = crv.TangentAt(t)
    tangent.Unitize()
    return tangent


def get_left_vectors(tangent: rg.Vector3d) -> Vector2D:
    length = math.hypot(tangent.X, tangent.Y)
    if length < EPS:
        raise ValueError(f"Invalid tangent vector: {tangent}")
    tx = tangent.X / length
    ty = tangent.Y / length
    left_vector = Vector2D(x=-ty, y=tx)
    return left_vector


def get_points_along_arc(start_point: rg.Point3d, end_point: rg.Point3d, type_info: typeInfo) -> tuple[list[rg.Point3d], list[float], list[rg.Vector3d], rg.Vector3d]:
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
    tangents_on_arc = [get_unitized_tangent(arc, d) for d in distances]
    end_tangent = tangents_on_arc[-1]
    return points_on_arc, distances, tangents_on_arc, end_tangent


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
    all_tangents: list[rg.Vector3d],
    segment_points: list[rg.Point3d],
    segment_STAs: list[float],
    segment_tangents: list[rg.Vector3d],
) -> None:
    if len(segment_points) != len(segment_STAs) or len(segment_points) != len(segment_tangents):
        raise ValueError(
            "points, STAs and tangents length mismatch: "
            f"points={len(segment_points)}, STAs={len(segment_STAs)}, tangents={len(segment_tangents)}"
        )
    start_idx = 1 if all_points else 0
    all_points.extend(segment_points[start_idx:])
    all_STAs.extend(segment_STAs[start_idx:])
    all_tangents.extend(segment_tangents[start_idx:])


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
    q = (k1 - k0) / L
    world_tangents = []
    for distance in distances:
        theta = rot_angle + k0 * distance + 0.5 * q * distance * distance
        world_tangent = rg.Vector3d(math.cos(theta), math.sin(theta), 0.0)
        world_tangent.Unitize()
        world_tangents.append(world_tangent)

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
    world_tangents[-1] = end_tangent
    return world_pts, distances, world_tangents, end_tangent

def get_indiv_center_line_points(
    road_center_info: RoadSurfaceInfo,
) -> tuple[list[rg.Point3d], list[Vector2D], list[float]]:
    plan_key_points = road_center_info.plan_Coord_infos
    plan_key_points = [const_point_obj(p) for p in plan_key_points]
    plan_key_points_STAs = road_center_info.plan_STAs
    type_infos = road_center_info.type_infos
    center_line_points_2D = []
    center_line_points_2D_STAs = []
    center_line_tangents_2D = []
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
            this_center_line_tangents_2D = [current_tangent, current_tangent]
        elif type_info.type == "arc":
            this_center_line_points_2D, distances, this_center_line_tangents_2D, current_tangent = get_points_along_arc(start_point, end_point, type_info)
            this_center_line_points_2D_STAs = [start_STA + distance for distance in distances]
        elif type_info.type == "clothoid":
            if current_tangent is None:
                current_tangent = get_chord_tangent(start_point, end_point)
            this_center_line_points_2D, distances, this_center_line_tangents_2D, end_tangent = make_clothoid_from_endpoints_radii(
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
            center_line_tangents_2D,
            this_center_line_points_2D,
            this_center_line_points_2D_STAs,
            this_center_line_tangents_2D,
        )
    z_infos = sorted(road_center_info.z_infos, key=lambda z_info: z_info.STA)
    zs = [z_info.z for z_info in z_infos]
    z_STAs = [z_info.STA for z_info in z_infos]
    z_pre_slopes = [z_info.pre_slope for z_info in z_infos]
    z_post_slopes = [z_info.post_slope for z_info in z_infos]
    center_line_points = []
    center_line_STAs = []
    left_vectors = []
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
        center_line_STAs.append(STA)
    for tangent in center_line_tangents_2D:
        left_vector = get_left_vectors(tangent)
        left_vectors.append(left_vector)
    return center_line_points, left_vectors, center_line_STAs


def interpolate_point_by_ratio(p0: rg.Point3d, p1: rg.Point3d, ratio: float) -> rg.Point3d:
    return rg.Point3d(
        p0.X + (p1.X - p0.X) * ratio,
        p0.Y + (p1.Y - p0.Y) * ratio,
        p0.Z + (p1.Z - p0.Z) * ratio,
    )


def interpolate_vector_by_ratio(v0: Vector2D, v1: Vector2D, ratio: float) -> Vector2D:
    x = v0.x + (v1.x - v0.x) * ratio
    y = v0.y + (v1.y - v0.y) * ratio
    length = math.hypot(x, y)
    if length < EPS:
        raise ValueError(f"Failed to interpolate left vector: {v0}, {v1}, ratio={ratio}")
    return Vector2D(x=x / length, y=y / length)


def get_center_sample_at_STA(
    target_STA: float,
    center_line_points: list[rg.Point3d],
    left_vectors: list[Vector2D],
    center_line_STAs: list[float],
) -> tuple[rg.Point3d, Vector2D, float]:
    for point, left_vector, STA in zip(center_line_points, left_vectors, center_line_STAs):
        if abs(STA - target_STA) < DISTANCE_TOL:
            return point, left_vector, STA

    for i in range(len(center_line_STAs) - 1):
        STA0 = center_line_STAs[i]
        STA1 = center_line_STAs[i + 1]
        if STA0 <= target_STA <= STA1:
            ratio = (target_STA - STA0) / (STA1 - STA0)
            point = interpolate_point_by_ratio(center_line_points[i], center_line_points[i + 1], ratio)
            left_vector = interpolate_vector_by_ratio(left_vectors[i], left_vectors[i + 1], ratio)
            return point, left_vector, target_STA

    raise ValueError(
        f"Target STA {target_STA} is out of center line range: "
        f"{center_line_STAs[0]} to {center_line_STAs[-1]}"
    )


def get_center_samples_in_STA_range(
    start_STA: float,
    end_STA: float,
    center_line_points: list[rg.Point3d],
    left_vectors: list[Vector2D],
    center_line_STAs: list[float],
) -> tuple[list[rg.Point3d], list[Vector2D], list[float]]:
    target_STAs = [start_STA]
    target_STAs.extend(
        STA for STA in center_line_STAs
        if start_STA + DISTANCE_TOL < STA < end_STA - DISTANCE_TOL
    )
    target_STAs.append(end_STA)
    samples = [
        get_center_sample_at_STA(
            target_STA=target_STA,
            center_line_points=center_line_points,
            left_vectors=left_vectors,
            center_line_STAs=center_line_STAs,
        )
        for target_STA in target_STAs
    ]
    sample_points, sample_left_vectors, sample_STAs = zip(*samples)
    return list(sample_points), list(sample_left_vectors), list(sample_STAs)


def get_slope_at_STA(target_STA: float, slope_STAs: list[float], slopes: list[float]) -> float:
    for STA, slope in zip(slope_STAs, slopes):
        if abs(STA - target_STA) < DISTANCE_TOL:
            return slope
    for i in range(len(slope_STAs) - 1):
        STA0 = slope_STAs[i]
        STA1 = slope_STAs[i + 1]
        if STA0 <= target_STA <= STA1:
            if abs(slopes[i + 1] - slopes[i]) < EPS:
                return slopes[i]
            return slopes[i] + (slopes[i + 1] - slopes[i]) * (target_STA - STA0) / (STA1 - STA0)
    raise ValueError(
        f"Target STA {target_STA} is out of slope range: "
        f"{slope_STAs[0]} to {slope_STAs[-1]}"
    )
    
def get_embankment_edge_points(
    center_line_points: list[rg.Point3d],
    left_vectors: list[Vector2D],
    center_line_STAs: list[float],
    embankment_pave_infos: list[EmbankmentPaveInfo],
) -> tuple[dict[int, list[rg.Point3d]], dict[int, list[rg.Point3d]], dict[int, list[float]]]:
    U_edge_points_dict = {}
    D_edge_points_dict = {}
    edge_STAs_dict = {}
    for i, embankment_pave_info in enumerate(embankment_pave_infos):
        slope_infos = sorted(embankment_pave_info.slope_infos, key=lambda s: s.STA)
        slope_STAs = [slope_info.STA for slope_info in slope_infos]
        slopes = [slope_info.slope for slope_info in slope_infos]
        width = embankment_pave_info.width
        U_edge_points = [] #Uがleft側、Dがright側
        D_edge_points = []
        target_center_points, target_left_vectors, target_STAs = get_center_samples_in_STA_range(
            start_STA=slope_STAs[0],
            end_STA=slope_STAs[-1],
            center_line_points=center_line_points,
            left_vectors=left_vectors,
            center_line_STAs=center_line_STAs,
        )
        for center_point, left_vector_2D, this_STA in zip(target_center_points, target_left_vectors, target_STAs):
            slope = get_slope_at_STA(this_STA, slope_STAs, slopes)
            left_vector_3D = rg.Vector3d(left_vector_2D.x, left_vector_2D.y, slope) #slopeはU側→D側の勾配なので、左（U）ベクトルに対してZ方向に加える
            right_vector_3D = rg.Vector3d(-left_vector_2D.x, -left_vector_2D.y, -slope) #右（D）ベクトルに対してZ方向に加える
            U_edge_point = center_point + left_vector_3D * width / 2
            D_edge_point = center_point + right_vector_3D * width / 2
            U_edge_points.append(U_edge_point)
            D_edge_points.append(D_edge_point)
        U_edge_points_dict[i] = U_edge_points
        D_edge_points_dict[i] = D_edge_points
        edge_STAs_dict[i] = target_STAs
    return U_edge_points_dict, D_edge_points_dict, edge_STAs_dict
    

def main(initial_or_final: str, debug=False):
    DIR = get_output_dir(initial_or_final)

    road_center_infos = load_from_pickle(DIR / f"{Filenames.INPUT}_{Filenames.ROAD_SURFACE}.pickle")
    center_line_info_dict = {}
    edge_info_dict = {}
    if debug:
        points = []
        for name, road_center_infos in road_center_infos.items():
            print(name)
            center_line_points, left_vectors, center_line_STAs = get_indiv_center_line_points(
                road_center_info = road_center_infos,
            )
            points.extend(center_line_points)
            if road_center_infos.embankment_pave_infos is not None:
                this_U_edge_points_dict, this_D_edge_points_dict, _ = get_embankment_edge_points(
                    center_line_points=center_line_points,
                    left_vectors=left_vectors,
                    center_line_STAs=center_line_STAs,
                    embankment_pave_infos=road_center_infos.embankment_pave_infos,
                )
                for _, U_edge_points in this_U_edge_points_dict.items():
                    points.extend(U_edge_points)
                for _, D_edge_points in this_D_edge_points_dict.items():
                    points.extend(D_edge_points)
        return points
    else:
        for name, road_center_infos in road_center_infos.items():
            print(name)
            center_line_points, left_vectors, center_line_STAs = get_indiv_center_line_points(
                road_center_info = road_center_infos,
            )
            center_line_info_dict[name] = {
                "STAs": center_line_STAs,
                "points": [const_3Dpoint(pt) for pt in center_line_points],
            }
            if road_center_infos.embankment_pave_infos is not None:
                this_U_edge_points_dict, this_D_edge_points_dict, this_edge_STAs_dict = get_embankment_edge_points(
                    center_line_points=center_line_points,
                    left_vectors=left_vectors,
                    center_line_STAs=center_line_STAs,
                    embankment_pave_infos=road_center_infos.embankment_pave_infos,
                )
                for n in this_edge_STAs_dict.keys():
                    edge_info_dict[f"{name}_{n}"] = {
                        "STAs": this_edge_STAs_dict[n],
                        "U_points": [const_3Dpoint(pt) for pt in this_U_edge_points_dict[n]],
                        "D_points": [const_3Dpoint(pt) for pt in this_D_edge_points_dict[n]],
                    }
        save_json_and_pickle(
            data = center_line_info_dict,
            folder_path = DIR,
            name = f"{Filenames.ROAD}_{Filenames.CENTER}_{Filenames.POINTS}",
        )
        save_json_and_pickle(
            data = edge_info_dict,
            folder_path = DIR,
            name = f"{Filenames.ROAD}_{Filenames.EDGE}_{Filenames.POINTS}",
        )
    return None





if __name__ == "__main__":
    points = main("initial")
    # points = main("initial", debug=True)
