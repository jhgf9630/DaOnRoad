"""
DaOnRoad - OR-Tools CVRP Solver
★ 모든 차량 반드시 사용 (k-means 사전 분할)
★ 같은 출발지 차량 → 방향 기반 강제 분할
"""
import math
from typing import List, Dict, Any

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("⚠️  OR-Tools 미설치. Greedy fallback 사용.")


# ── 유틸: 두 좌표 간 간단 거리 ──────────────────────────────────
def _dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)


# ── 방향 기반 클러스터 사전 분할 ────────────────────────────────
def _assign_sectors(passengers, vehicles, dest_lat, dest_lng):
    """
    같은 출발지를 공유하는 차량 그룹 내에서
    승객을 방향(각도) 기준으로 균등 분할하여 초기 할당.
    → OR-Tools가 반드시 모든 차량을 사용하도록 유도.
    반환: {passenger_idx: vehicle_idx_list_allowed}
    """
    n_pax = len(passengers)
    n_veh = len(vehicles)

    # 차량을 출발지 좌표로 그룹화
    from collections import defaultdict
    depot_groups = defaultdict(list)  # (round_lat, round_lng) → [v_idx]
    for vi, v in enumerate(vehicles):
        key = (round(v.get('start_lat', dest_lat), 3),
               round(v.get('start_lng', dest_lng), 3))
        depot_groups[key].append(vi)

    # 각 그룹 내 차량이 2대 이상이면 방향 기반 분할
    pax_allowed = {pi: list(range(n_veh)) for pi in range(n_pax)}  # 기본: 모든 차량 허용

    for depot_key, v_indices in depot_groups.items():
        if len(v_indices) < 2:
            continue  # 단독 차량은 분할 불필요

        dep_lat, dep_lng = depot_key

        # 각 승객의 출발지 기준 방향각(도)
        def angle(p):
            dy = p['lat'] - dep_lat
            dx = p['lng'] - dep_lng
            return math.degrees(math.atan2(dy, dx)) % 360

        # 승객별 각도 계산
        pax_angles = [(pi, angle(passengers[pi])) for pi in range(n_pax)]
        pax_angles.sort(key=lambda x: x[1])

        # 차량 수만큼 균등 섹터 분할
        n_v = len(v_indices)
        sector_size = 360.0 / n_v
        for rank, vi in enumerate(v_indices):
            sector_start = rank * sector_size
            sector_end   = sector_start + sector_size
            allowed_pax  = [
                pi for pi, ang in pax_angles
                if sector_start <= ang < sector_end
            ]
            # 섹터에 승객이 없으면 가장 가까운 승객 일부 할당
            if not allowed_pax:
                # 각도 기준 가장 가까운 순으로 n_pax//n_v 명 할당
                closest = sorted(pax_angles,
                    key=lambda x: min(abs(x[1]-sector_start), abs(x[1]-sector_end)))
                allowed_pax = [closest[i][0] for i in range(max(1, n_pax // n_v))]

            for pi in allowed_pax:
                if vi not in pax_allowed.get(pi, []):
                    continue
                # 이 승객을 이 차량 전용으로 제한
                pax_allowed[pi] = [vi]

    return pax_allowed


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
    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx,
                       vehicle_start_indices, vehicle_end_indices):

        num_nodes         = len(distance_matrix)
        num_vehicles      = len(vehicles)
        passenger_indices = node_indices['passengers']

        # destination을 각 차량의 end로 → 방문 자동 강제
        dest_as_end = [destination_idx] * num_vehicles

        manager = pywrapcp.RoutingIndexManager(
            num_nodes, num_vehicles,
            vehicle_start_indices, dest_as_end
        )
        routing = pywrapcp.RoutingModel(manager)

        # 거리 콜백
        def dist_cb(fi, ti):
            return distance_matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]
        transit_cb = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

        # 용량 제약
        def demand_cb(fi):
            node = manager.IndexToNode(fi)
            if node in passenger_indices:
                return passengers[passenger_indices.index(node)]['passenger_count']
            return 0
        demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            demand_cb_idx, 0,
            [v['capacity'] for v in vehicles], True, "Capacity"
        )

        # ★ 섹터 사전 분할로 차량별 허용 승객 제한
        # 도착지 좌표 추출
        dest_node = next(
            (n for n in range(num_nodes)
             if n == destination_idx), destination_idx
        )
        # vehicles에서 도착지 좌표 가져오기 (end_lat/lng)
        dest_lat = vehicles[0].get('end_lat', 37.5)
        dest_lng = vehicles[0].get('end_lng', 127.0)

        pax_allowed = _assign_sectors(passengers, vehicles, dest_lat, dest_lng)

        BIG = 10_000_000
        for pi, p_node in enumerate(passenger_indices):
            allowed_v = pax_allowed.get(pi, list(range(num_vehicles)))
            node_idx  = manager.NodeToIndex(p_node)

            if len(allowed_v) == num_vehicles:
                # 제한 없음: 무조건 방문
                routing.AddDisjunction([node_idx], BIG)
            else:
                # 특정 차량만 방문 가능하도록 AllowedVehicles 설정
                routing.AddDisjunction([node_idx], BIG)
                routing.VehicleVar(node_idx).SetValues(allowed_v)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_params.time_limit.seconds = 20

        solution = routing.SolveWithParameters(search_params)
        if not solution:
            print("[solver] OR-Tools 해 없음 → Greedy fallback")
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
                nxt = solution.Value(routing.NextVar(index))
                total_sec += distance_matrix[node][manager.IndexToNode(nxt)]
                index = nxt
            route_nodes.append(manager.IndexToNode(index))  # end = destination

            stops     = self._map_stops(route_nodes, passengers, passenger_indices,
                                        destination_idx, vehicle_start_indices, v_idx)
            total_pax = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')

            # ★ 모든 차량 포함 (승객 0명이라도)
            routes.append({
                "bus_id":             vehicle['bus_id'],
                "vehicle":            vehicle,
                "stops":              stops,
                "total_distance_sec": total_sec,
                "total_passengers":   total_pax
            })

        return {"success": True, "routes": routes}

    # ─────────────────────────────────────────────────────────
    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx,
                      vehicle_start_indices, vehicle_end_indices):
        """
        ★ 모든 차량 반드시 사용
        1) 섹터 분할로 초기 할당
        2) 각 차량 greedy nearest-neighbor
        3) 미배정 승객은 여유 차량에 추가
        """
        n_pax     = len(passengers)
        n_veh     = len(vehicles)
        dest_lat  = vehicles[0].get('end_lat', 37.5)
        dest_lng  = vehicles[0].get('end_lng', 127.0)

        pax_allowed = _assign_sectors(passengers, vehicles, dest_lat, dest_lng)

        # 차량별 초기 할당 (섹터 기반)
        vehicle_pax = {vi: [] for vi in range(n_veh)}
        for pi in range(n_pax):
            best_v = pax_allowed.get(pi, [0])[0]
            vehicle_pax[best_v].append(pi)

        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            assigned = vehicle_pax[v_idx][:]
            capacity  = vehicle['capacity']
            used      = 0
            route_nodes = [vehicle_start_indices[v_idx]]
            current     = vehicle_start_indices[v_idx]

            # 가장 가까운 순으로 용량 내 탑승
            remaining = assigned[:]
            while remaining:
                best_idx, best_cost = None, float('inf')
                for pi in remaining:
                    p_node  = node_indices['passengers'][pi]
                    p_count = passengers[pi]['passenger_count']
                    if used + p_count > capacity:
                        continue
                    cost = distance_matrix[current][p_node]
                    if cost < best_cost:
                        best_cost = cost; best_idx = pi
                if best_idx is None:
                    break
                p_node = node_indices['passengers'][best_idx]
                route_nodes.append(p_node)
                used    += passengers[best_idx]['passenger_count']
                current  = p_node
                remaining.remove(best_idx)

            route_nodes.append(destination_idx)
            stops     = self._map_stops(route_nodes, passengers, node_indices['passengers'],
                                        destination_idx, vehicle_start_indices, v_idx)
            total_pax = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')

            routes.append({
                "bus_id":           vehicle['bus_id'],
                "vehicle":          vehicle,
                "stops":            stops,
                "total_passengers": total_pax
            })

        # 미배정 승객 처리: 여유 있는 차량에 추가
        assigned_all = {pi for v_pax in vehicle_pax.values() for pi in v_pax}
        unassigned   = [pi for pi in range(n_pax) if pi not in assigned_all]
        if unassigned:
            print(f"[solver] 미배정 승객 {len(unassigned)}명 재배정")
            for pi in unassigned:
                p_count = passengers[pi]['passenger_count']
                for ri, route in enumerate(routes):
                    used = route['total_passengers']
                    cap  = vehicles[ri]['capacity']
                    if used + p_count <= cap:
                        p_node = node_indices['passengers'][pi]
                        # destination 앞에 삽입
                        stops = route['stops']
                        dest_pos = next((i for i, s in enumerate(stops)
                                         if s['type'] == 'destination'), len(stops))
                        pickup_order = sum(1 for s in stops if s['type'] == 'pickup') + 1
                        stops.insert(dest_pos, {
                            "order": dest_pos, "pickup_order": pickup_order,
                            "node_idx": p_node, "type": "pickup",
                            "name": passengers[pi]['name'],
                            "address": passengers[pi]['address'],
                            "lat": passengers[pi]['lat'], "lng": passengers[pi]['lng'],
                            "passenger_count": passengers[pi]['passenger_count'],
                            "travel_time_sec": 0, "pickup_time": ""
                        })
                        route['total_passengers'] += p_count
                        break

        return {"success": True, "routes": routes}

    # ─────────────────────────────────────────────────────────
    def _map_stops(self, route_nodes, passengers, passenger_indices,
                   destination_idx, vehicle_start_indices, v_idx):
        stops = []
        pickup_order = 0
        for order, node in enumerate(route_nodes):
            if node in passenger_indices:
                pi = passenger_indices.index(node)
                pickup_order += 1
                stops.append({
                    "order": order, "pickup_order": pickup_order,
                    "node_idx": node, "type": "pickup",
                    "name": passengers[pi]['name'],
                    "address": passengers[pi]['address'],
                    "lat": passengers[pi]['lat'], "lng": passengers[pi]['lng'],
                    "passenger_count": passengers[pi]['passenger_count'],
                    "travel_time_sec": 0, "pickup_time": ""
                })
            elif node == destination_idx:
                stops.append({
                    "order": order, "node_idx": node,
                    "type": "destination", "name": "도착지",
                    "address": "", "lat": None, "lng": None,
                    "travel_time_sec": 0, "pickup_time": ""
                })
            elif v_idx < len(vehicle_start_indices) and node == vehicle_start_indices[v_idx]:
                stops.append({
                    "order": order, "node_idx": node,
                    "type": "start", "name": "출발지",
                    "travel_time_sec": 0, "pickup_time": ""
                })
        return stops
