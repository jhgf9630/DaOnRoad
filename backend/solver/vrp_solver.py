"""
DaOnRoad - OR-Tools CVRP Solver
"""
from typing import List, Dict, Any

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("⚠️  OR-Tools 미설치. Greedy fallback 사용.")


class VRPSolver:
    def solve(self, distance_matrix, passengers, vehicles,
              node_indices, destination_idx,
              vehicle_start_indices, vehicle_end_indices):

        if ORTOOLS_AVAILABLE:
            return self._solve_ortools(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )
        return self._solve_greedy(
            distance_matrix, passengers, vehicles,
            node_indices, destination_idx,
            vehicle_start_indices, vehicle_end_indices
        )

    # ─────────────────────────────────────────────────────────
    # OR-Tools solver
    # ─────────────────────────────────────────────────────────
    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx,
                       vehicle_start_indices, vehicle_end_indices):

        num_nodes        = len(distance_matrix)
        num_vehicles     = len(vehicles)
        passenger_indices = node_indices['passengers']

        # ★ 핵심 수정: destination을 각 차량의 end node로 사용
        #   → destination 방문이 자동으로 강제됨
        #   → start/end 가 같은 노드 문제도 해소
        dest_as_end = [destination_idx] * num_vehicles

        manager = pywrapcp.RoutingIndexManager(
            num_nodes, num_vehicles,
            vehicle_start_indices,
            dest_as_end          # ★ end = destination
        )
        routing = pywrapcp.RoutingModel(manager)

        # 거리 콜백
        def dist_cb(from_idx, to_idx):
            return distance_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

        transit_cb = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

        # 용량 제약
        def demand_cb(from_idx):
            node = manager.IndexToNode(from_idx)
            if node in passenger_indices:
                return passengers[passenger_indices.index(node)]['passenger_count']
            return 0

        demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            demand_cb_idx, 0,
            [v['capacity'] for v in vehicles],
            True, "Capacity"
        )

        # ★ 핵심 수정: penalty를 크게 설정 → 모든 승객 반드시 방문
        BIG_PENALTY = 10_000_000
        for p_node in passenger_indices:
            routing.AddDisjunction([manager.NodeToIndex(p_node)], BIG_PENALTY)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_params.time_limit.seconds = 15

        solution = routing.SolveWithParameters(search_params)
        if not solution:
            print("OR-Tools 해 없음 → Greedy fallback")
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )

        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            route_nodes = []
            index = routing.Start(v_idx)
            total_sec = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route_nodes.append(node)
                next_index = solution.Value(routing.NextVar(index))
                total_sec += distance_matrix[node][manager.IndexToNode(next_index)]
                index = next_index

            # end node (= destination) 추가
            route_nodes.append(manager.IndexToNode(index))

            stops = self._map_stops(
                route_nodes, passengers, passenger_indices,
                destination_idx, vehicle_start_indices, v_idx
            )
            total_pax = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')

            if total_pax > 0:
                routes.append({
                    "bus_id":           vehicle['bus_id'],
                    "vehicle":          vehicle,
                    "stops":            stops,
                    "total_distance_sec": total_sec,
                    "total_passengers": total_pax
                })

        return {"success": True, "routes": routes}

    # ─────────────────────────────────────────────────────────
    # Greedy fallback (OR-Tools 없을 때)
    # ─────────────────────────────────────────────────────────
    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx,
                      vehicle_start_indices, vehicle_end_indices):

        unassigned = list(range(len(passengers)))
        routes = []

        for v_idx, vehicle in enumerate(vehicles):
            if not unassigned:
                break
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
                        best_cost = cost
                        best_idx  = i
                if best_idx is None:
                    break
                p_node = node_indices['passengers'][best_idx]
                route_nodes.append(p_node)
                used    += passengers[best_idx]['passenger_count']
                current  = p_node
                unassigned.remove(best_idx)

            route_nodes.append(destination_idx)

            stops = self._map_stops(
                route_nodes, passengers, node_indices['passengers'],
                destination_idx, vehicle_start_indices, v_idx
            )
            total_pax = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')

            if total_pax > 0:
                routes.append({
                    "bus_id":           vehicle['bus_id'],
                    "vehicle":          vehicle,
                    "stops":            stops,
                    "total_passengers": total_pax
                })

        return {"success": True, "routes": routes}

    # ─────────────────────────────────────────────────────────
    # 노드 → stop 딕셔너리 변환
    # ─────────────────────────────────────────────────────────
    def _map_stops(self, route_nodes, passengers, passenger_indices,
                   destination_idx, vehicle_start_indices, v_idx):
        stops = []
        pickup_order = 0

        for order, node in enumerate(route_nodes):
            if node in passenger_indices:
                p_idx = passenger_indices.index(node)
                pickup_order += 1
                stops.append({
                    "order":           order,
                    "pickup_order":    pickup_order,
                    "node_idx":        node,
                    "type":            "pickup",
                    "name":            passengers[p_idx]['name'],
                    "address":         passengers[p_idx]['address'],
                    "lat":             passengers[p_idx]['lat'],
                    "lng":             passengers[p_idx]['lng'],
                    "passenger_count": passengers[p_idx]['passenger_count'],
                    "travel_time_sec": 0,
                    "pickup_time":     ""
                })
            elif node == destination_idx:
                stops.append({
                    "order":           order,
                    "node_idx":        node,
                    "type":            "destination",
                    "name":            "도착지",
                    "address":         "",   # routing.py에서 채움
                    "lat":             None,
                    "lng":             None,
                    "travel_time_sec": 0,
                    "pickup_time":     ""
                })
            elif v_idx < len(vehicle_start_indices) and node == vehicle_start_indices[v_idx]:
                stops.append({
                    "order":           order,
                    "node_idx":        node,
                    "type":            "start",
                    "name":            "출발지",
                    "travel_time_sec": 0,
                    "pickup_time":     ""
                })

        return stops
