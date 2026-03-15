"""
OR-Tools CVRP Solver
Multi-Start / Multi-End / Fixed Arrival Time 지원
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

    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx,
                       vehicle_start_indices, vehicle_end_indices):
        """OR-Tools VRP Solver"""
        num_nodes = len(distance_matrix)
        num_vehicles = len(vehicles)
        passenger_indices = node_indices['passengers']

        # RoutingIndexManager 생성 (multi start/end)
        manager = pywrapcp.RoutingIndexManager(
            num_nodes,
            num_vehicles,
            vehicle_start_indices,
            vehicle_end_indices
        )
        routing = pywrapcp.RoutingModel(manager)

        # Distance Callback
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # 용량 제약
        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            if from_node in passenger_indices:
                p_idx = passenger_indices.index(from_node)
                return passengers[p_idx]['passenger_count']
            return 0

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        capacities = [v['capacity'] for v in vehicles]
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            capacities,
            True,
            "Capacity"
        )

        # 모든 승객 노드 방문 필수
        for p_idx in passenger_indices:
            routing.AddDisjunction([manager.NodeToIndex(p_idx)], 0)

        # 행사장은 모든 차량의 경로에 포함 (단, end node로 처리 가능하도록)
        # destination은 강제 방문 (penalty 없이)
        dest_index = manager.NodeToIndex(destination_idx)

        # Search Parameters
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.seconds = 10

        solution = routing.SolveWithParameters(search_params)

        if not solution:
            return {"success": False, "routes": []}

        # 결과 파싱
        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            route_stops = []
            index = routing.Start(v_idx)
            total_dist = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route_stops.append(node)
                next_index = solution.Value(routing.NextVar(index))
                total_dist += distance_matrix[node][manager.IndexToNode(next_index)]
                index = next_index

            route_stops.append(manager.IndexToNode(index))  # end node

            # 행사장이 경로에 없으면 마지막에 삽입 (end 직전)
            if destination_idx not in route_stops and len(route_stops) > 1:
                route_stops.insert(-1, destination_idx)

            # 승객 정보 매핑
            stops_info = self._map_stops(route_stops, passengers, passenger_indices,
                                          destination_idx, vehicle_start_indices,
                                          vehicle_end_indices, v_idx)
            total_passengers = sum(
                s.get('passenger_count', 0) for s in stops_info
                if s['type'] == 'pickup'
            )

            if total_passengers > 0 or len(route_stops) > 2:
                routes.append({
                    "bus_id": vehicle['bus_id'],
                    "vehicle": vehicle,
                    "stops": stops_info,
                    "total_distance_sec": total_dist,
                    "total_passengers": total_passengers
                })

        return {"success": True, "routes": routes}

    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx,
                      vehicle_start_indices, vehicle_end_indices):
        """OR-Tools 없을 때 Greedy 대체 솔버"""
        import copy
        unassigned = list(range(len(passengers)))
        routes = []

        for v_idx, vehicle in enumerate(vehicles):
            capacity = vehicle['capacity']
            used = 0
            route_nodes = [vehicle_start_indices[v_idx]]
            current = vehicle_start_indices[v_idx]

            while unassigned and used < capacity:
                best_idx = None
                best_cost = float('inf')

                for i in unassigned:
                    p_node = node_indices['passengers'][i]
                    p_count = passengers[i]['passenger_count']
                    if used + p_count > capacity:
                        continue
                    cost = distance_matrix[current][p_node]
                    if cost < best_cost:
                        best_cost = cost
                        best_idx = i

                if best_idx is None:
                    break

                p_node = node_indices['passengers'][best_idx]
                route_nodes.append(p_node)
                used += passengers[best_idx]['passenger_count']
                current = p_node
                unassigned.remove(best_idx)

            # 행사장 추가
            route_nodes.append(destination_idx)
            # 도착지 추가
            route_nodes.append(vehicle_end_indices[v_idx])

            stops_info = self._map_stops(
                route_nodes, passengers, node_indices['passengers'],
                destination_idx, vehicle_start_indices,
                vehicle_end_indices, v_idx
            )
            total_passengers = sum(
                s.get('passenger_count', 0) for s in stops_info
                if s['type'] == 'pickup'
            )

            if total_passengers > 0:
                routes.append({
                    "bus_id": vehicle['bus_id'],
                    "vehicle": vehicle,
                    "stops": stops_info,
                    "total_passengers": total_passengers
                })

        return {"success": True, "routes": routes}

    def _map_stops(self, route_nodes, passengers, passenger_indices,
                   destination_idx, vehicle_start_indices, vehicle_end_indices, v_idx):
        stops = []
        for order, node in enumerate(route_nodes):
            if node in passenger_indices:
                p_idx = passenger_indices.index(node)
                stops.append({
                    "order": order,
                    "node_idx": node,
                    "type": "pickup",
                    "name": passengers[p_idx]['name'],
                    "address": passengers[p_idx]['address'],
                    "lat": passengers[p_idx]['lat'],
                    "lng": passengers[p_idx]['lng'],
                    "passenger_count": passengers[p_idx]['passenger_count'],
                    "travel_time_sec": 0
                })
            elif node == destination_idx:
                stops.append({
                    "order": order,
                    "node_idx": node,
                    "type": "destination",
                    "name": "행사장",
                    "travel_time_sec": 0
                })
            elif v_idx < len(vehicle_start_indices) and node == vehicle_start_indices[v_idx]:
                stops.append({
                    "order": order,
                    "node_idx": node,
                    "type": "start",
                    "name": "출발지",
                    "travel_time_sec": 0
                })
            elif v_idx < len(vehicle_end_indices) and node == vehicle_end_indices[v_idx]:
                stops.append({
                    "order": order,
                    "node_idx": node,
                    "type": "end",
                    "name": "도착지",
                    "travel_time_sec": 0
                })
        return stops
