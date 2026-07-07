import Rhino
import Rhino.Geometry as rg


def get_named_points_on_layer(layer_index: int) -> dict[str, rg.Point3d]:
    rhdoc = Rhino.RhinoDoc.ActiveDoc
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.LayerIndex = int(layer_index)
    point_dict = {}
    for rhino_obj in rhdoc.Objects.GetObjectList(settings):
        geometry = rhino_obj.Geometry
        if not isinstance(geometry, rg.Point):
            continue
        name = rhino_obj.Attributes.Name
        if not name:
            continue
        if name in point_dict:
            raise ValueError(f"Duplicate point name on layer index {layer_index}: {name}")
        point_dict[name] = geometry.Location
    return point_dict
