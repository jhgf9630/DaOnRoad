"""
DaOnRoad - OR-Tools CVRP Solver
Multi-Start / Fixed Arrival Time 지원
"""
from typing import List, Dict, Any, Optional

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("⚠️  OR-Tools 미설치. Greedy fallback 사용.")


class VRPSolver:
    def solve(self,
              distance_matrix: List[List[int]],
              passengers: List[Dict],
              vehicles: List[Dict],
              node_indices: Dict,
              destination_idx: int,
              vehicle_start_indices: List[int],
              vehicle_end_indices: List[int]) -> Dict[str, Any]:

        if ORTOOLS_AVAILABLE:
            return self._solve_ortools(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )
        else:
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )

    # ──────────────────────────────────────────
    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx,
                       vehicle_start_indices, vehicle_end_indices):
        num_nodes    = len(distance_matrix)
        num_vehicles = len(vehicles)
        passenger_indices = node_indices['passengers']

        manager = pywrapcp.RoutingIndexManager(
            num_nodes, num_vehicles,
            vehicle_start_indices, vehicle_end_indices
        )
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

        transit_cb = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

        def demand_callback(from_index):
            node = manager.IndexToNode(from_index)
            if node in passenger_indices:
                return passengers[passenger_indices.index(node)]['passenger_count']
            return 0

        demand_cb = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_cb, 0, [v['capacity'] for v in vehicles], True, "Capacity"
        )

        for p_node in passenger_indices:
            routing.AddDisjunction([manager.NodeToIndex(p_node)], 0)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_params.time_limit.seconds = 10

        solution = routing.SolveWithParameters(search_params)
        if not solution:
            return {"success": False, "routes": []}

        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            route_nodes = []
            index = routing.Start(v_idx)
            total_dist = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route_nodes.append(node)
                next_index = solution.Value(routing.NextVar(index))
                total_dist += distance_matrix[node][manager.IndexToNode(next_index)]
                index = next_index
            route_nodes.append(manager.IndexToNode(index))  # end node

            # destination이 경로에 없으면 end 직전에 삽입
            if destination_idx not in route_nodes and len(route_nodes) > 1:
                route_nodes.insert(-1, destination_idx)

            stops_info = self._map_stops(
                route_nodes, passengers, passenger_indices,
                destination_idx, vehicle_start_indices, vehicle_end_indices, v_idx
            )
            total_pax = sum(s['passenger_count'] for s in stops_info if s['type'] == 'pickup')

            if total_pax > 0:
                routes.append({
                    "bus_id": vehicle['bus_id'],
                    "vehicle": vehicle,
                    "stops": stops_info,
                    "total_distance_sec": total_dist,
                    "total_passengers": total_pax
                })

        return {"success": True, "routes": routes}

    # ──────────────────────────────────────────
    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx,
                      vehicle_start_indices, vehicle_end_indices):
        unassigned = list(range(len(passengers)))
        routes = []

        for v_idx, vehicle in enumerate(vehicles):
            capacity = vehicle['capacity']
            used = 0
            route_nodes = [vehicle_start_indices[v_idx]]
            current = vehicle_start_indices[v_idx]

            while unassigned and used < capacity:
                best_idx, best_cost = None, float('inf')
                for i in unassigned:
                    p_node  = node_indices['passengers'][i]
                    p_count = passengers[i]['passenger_count']
                    if used + p_count > capacity:
                        continue
                    cost = distance_matrix[current][p_node]
                    if cost < best_cost:
                        best_cost = cost; best_idx = i
                if best_idx is None:
                    break
                p_node = node_indices['passengers'][best_idx]
                route_nodes.append(p_node)
                used    += passengers[best_idx]['passenger_count']
                current  = p_node
                unassigned.remove(best_idx)

            route_nodes.append(destination_idx)
            route_nodes.append(vehicle_end_indices[v_idx])

            stops_info = self._map_stops(
                route_nodes, passengers, node_indices['passengers'],
                destination_idx, vehicle_start_indices, vehicle_end_indices, v_idx
            )
            total_pax = sum(s['passenger_count'] for s in stops_info if s['type'] == 'pickup')

            if total_pax > 0:
                routes.append({
                    "bus_id": vehicle['bus_id'],
                    "vehicle": vehicle,
                    "stops": stops_info,
                    "total_passengers": total_pax
                })

        return {"success": True, "routes": routes}

    # ──────────────────────────────────────────
    def _map_stops(self, route_nodes, passengers, passenger_indices,
                   destination_idx, vehicle_start_indices, vehicle_end_indices, v_idx):
        """
        노드 목록 → stop 딕셔너리 목록
        ★ 모든 stop에 lat/lng 포함 (지도 렌더링 필수)
        ★ pickup_order: pickup 정류장만 세는 순서 (1부터)
        """
        stops = []
        pickup_order = 0

        for order, node in enumerate(route_nodes):
            if node in passenger_indices:
                p_idx = passenger_indices.index(node)
                pickup_order += 1
                stops.append({
                    "order":          order,
                    "pickup_order":   pickup_order,   # ★ 픽업 순서
                    "node_idx":       node,
                    "type":           "pickup",
                    "name":           passengers[p_idx]['name'],
                    "address":        passengers[p_idx]['address'],
                    "lat":            passengers[p_idx]['lat'],    # ★
                    "lng":            passengers[p_idx]['lng'],    # ★
                    "passenger_count": passengers[p_idx]['passenger_count'],
                    "travel_time_sec": 0,
                    "pickup_time":    ""
                })
            elif node == destination_idx:
                stops.append({
                    "order":      order,
                    "node_idx":   node,
                    "type":       "destination",
                    "name":       "도착지",
                    "address":    "",          # routing.py에서 실제 주소 채워줌
                    "lat":        None,        # routing.py에서 채워줌
                    "lng":        None,
                    "travel_time_sec": 0,
                    "pickup_time": ""
                })
            elif v_idx < len(vehicle_start_indices) and node == vehicle_start_indices[v_idx]:
                stops.append({
                    "order":      order,
                    "node_idx":   node,
                    "type":       "start",
                    "name":       "출발지",
                    "travel_time_sec": 0,
                    "pickup_time": ""
                })
            elif v_idx < len(vehicle_end_indices) and node == vehicle_end_indices[v_idx]:
                stops.append({
                    "order":      order,
                    "node_idx":   node,
                    "type":       "end",
                    "name":       "도착지",
                    "travel_time_sec": 0,
                    "pickup_time": ""
                })

        return stops
