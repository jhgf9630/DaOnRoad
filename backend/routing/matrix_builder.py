"""One node per input group, one common destination, one start per vehicle."""
import math
import os
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from routing.distance_cache import DistanceCache
from routing.haversine import build_haversine_matrix
from routing.osrm_service import build_osrm_matrix, get_route_polyline, _is_local


class MatrixBuilder:
    def _build_nodes(self, passengers, vehicles, destination):
        nodes = [{'lat': p['lat'], 'lng': p['lng']} for p in passengers]
        dest = len(nodes)
        nodes.append({'lat': destination['lat'], 'lng': destination['lng']})
        starts = []
        for vehicle in vehicles:
            starts.append(len(nodes))
            nodes.append({'lat': vehicle['start_lat'], 'lng': vehicle['start_lng']})
        ends = [dest] * len(vehicles)
        indices = dict(passengers=list(range(len(passengers))), destination=dest,
                       vehicle_starts=starts, vehicle_ends=ends)
        return nodes, indices, dest, starts, ends

    def build(self, passengers, vehicles, destination, progress=None, travel_time_factor=1.0):
        nodes, indices, dest, starts, ends = self._build_nodes(passengers, vehicles, destination)
        if os.environ.get('OSRM_BASE_URL', '').strip():
            matrix, source = build_osrm_matrix(nodes, progress=progress)
        else:
            matrix, source = build_haversine_matrix(nodes), 'haversine'
        matrix = [[math.ceil(value * travel_time_factor) for value in row] for row in matrix]
        return dict(matrix=matrix, matrix_source=source, nodes=nodes, node_indices=indices,
                    destination_idx=dest, vehicle_start_indices=starts, vehicle_end_indices=ends)

    def refine_with_road_api(self, routes, matrix_result, progress=None):
        nodes = matrix_result['nodes']
        use_osrm = matrix_result['matrix_source'].startswith('osrm')
        cache = DistanceCache('osrm_route_cache.json')
        segments = [(r, i, a['node_idx'], b['node_idx']) for r in routes
                    for i, (a,b) in enumerate(zip(r['stops'], r['stops'][1:]))]
        for r in routes:
            r['polylines'] = [None] * (len(r['stops']) - 1)
            r['polyline_sources'] = ['estimated'] * (len(r['stops']) - 1)
        def fetch(segment):
            _, _, a, b = segment
            return get_route_polyline(nodes[a], nodes[b], cache) if use_osrm else None
        # Bound concurrency on our own server; public hosts remain sequential.
        workers = 4 if _is_local() else 1
        pool = ThreadPoolExecutor(max_workers=workers)
        waiting = deque()
        remaining = iter(segments)
        try:
            for segment in list(segments[:workers]):
                next(remaining)
                waiting.append((segment, pool.submit(fetch, segment)))
            completed = 0
            while waiting:
                segment, future = waiting.popleft()
                poly = future.result()
                route, i, a, b = segment
                route['polylines'][i] = poly or [[nodes[a]['lat'], nodes[a]['lng']], [nodes[b]['lat'], nodes[b]['lng']]]
                route['polyline_sources'][i] = 'osrm' if poly else 'estimated'
                completed += 1
                if progress:
                    progress(completed, len(segments))
                segment = next(remaining, None)
                if segment is not None:
                    waiting.append((segment, pool.submit(fetch, segment)))
        finally:
            # At most four requests are in flight; cancellation never drains a
            # queue containing hundreds of yet-to-start road requests.
            for _, future in waiting:
                future.cancel()
            pool.shutdown(wait=True, cancel_futures=True)
