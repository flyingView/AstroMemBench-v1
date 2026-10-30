"""Physical movement along explicitly identified edges, including parallel corridors."""


def traverse(graph,route,passable):
    edges = {edge['id']:edge for edge in graph['edges']}
    visited,traversed,distance = [route['nodes'][0]],[],0
    blocked = None
    for edge_id,destination in zip(route['edges'],route['nodes'][1:],strict=True):
        if not passable[edge_id]:
            blocked = edge_id
            break
        traversed.append(edge_id)
        visited.append(destination)
        distance += edges[edge_id]['length_m']
    return {'location':visited[-1],'visited_nodes':visited,'traversed_edges':traversed,'travelled_m':distance,
            'blocked_edge':blocked,'arrived':blocked is None}
