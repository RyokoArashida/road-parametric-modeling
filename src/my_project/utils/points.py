from Rhino import Geometry as rg

def get_point_dict(point_dict:  dict[str,tuple[float, float, float]]) -> dict[str, rg.Point3d]:
    return {key: rg.Point3d(*coords) for key, coords in point_dict.items()}
