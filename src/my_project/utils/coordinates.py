from pyproj import CRS, Transformer

original_EPSG = 30168 # 平面直角座標系、旧日本測地系、静岡県
wgs84_EPSG = 4326 # WGS84

def to_world_coordinates(
    x: float, # 図面上のx座標（日本測地系）-82543.2004とか
    y: float, # 図面上のy座標（日本測地系）37693.6124とか
) -> tuple[float, float]:
    transformer = Transformer.from_crs(
        CRS.from_epsg(original_EPSG),
        CRS.from_epsg(wgs84_EPSG),
        always_xy=True
    )
    lon, lat = transformer.transform(y, x) # yが経度、xが緯度
    return lat, lon # 緯度、経度の順で返す

def to_world_coordinates_batch(
    coordinates: list[tuple[float, float]], # 図面上の座標のリスト
) -> list[tuple[float, float]]: # 緯度、経度のリスト
    return [to_world_coordinates(x, y) for x, y in coordinates]

