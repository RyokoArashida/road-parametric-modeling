from my_project.config.schemas.embankment_pavement_schemas import EmbankmentPaveInfo


def get_edge_info(pavement_info: EmbankmentPaveInfo, edge: str):
    return pavement_info.start_edge if edge == "start" else pavement_info.end_edge


def get_edge_structure(pavement_info: EmbankmentPaveInfo, edge: str):
    edge_info = get_edge_info(pavement_info, edge)
    if edge_info is not None and edge_info.structure is not None:
        return edge_info.structure
    return None
