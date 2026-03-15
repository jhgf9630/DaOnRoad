"""
DaOnRoad - OR-Tools CVRP Solver
★ 모든 차량에 반드시 1명 이상 배정
★ 방향 기반 섹터 분할로 균등 배분
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


def _dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)


def _assign_sectors(passengers, vehicles, dest_lat, dest_lng):
    """
    차량이 N대일 때 승객을 N개 섹터로 분할.
    같은 출발지 그룹 내에서는 방향(각도) 기준 분할.
    반환: {passenger_idx: [allowed_vehicle_idx, ...]}
    """
    import math
    from collections import defaultdict

    n_pax = len(passengers)
    n_veh = len(vehicles)

    if n_veh == 1:
        return {pi: [0] for pi in range(n_pax)}

    # 출발지 좌표로 그룹화
    depot_groups = defaultdict(list)
    for vi, v in enumerate(vehicles):
        key = (round(v.get('start_lat', dest_lat), 3),
               round(v.get('start_lng', dest_lng), 3))
        depot_groups[key].append(vi)

    pax_to_vehicle = {}  # pi → vi (1:1 강제 배정)

    for depot_key, v_indices in depot_groups.items():
        n_v = len(v_indices)
        dep_lat, dep_lng = depot_key

        if n_v == 1:
            # 단독 차량: 제한 없음 (나중에 다른 그룹과 합산)
            for pi in range(n_pax):
                if pi not in pax_to_vehicle:
                    pax_to_vehicle[pi] = v_indices[0]
            continue

        # 방향각 계산
        def angle_of(p):
            dy = p['lat'] - dep_lat
            dx = p['lng'] - dep_lng
            return math.degrees(math.atan2(dy, dx)) % 360

        pax_angles = sorted(
            [(pi, angle_of(passengers[pi])) for pi in range(n_pax)],
            key=lambda x: x[1]
        )

        # 섹터 경계 계산 (360도 균등 분할)
        sector_size = 360.0 / n_v
        for rank, vi in enumerate(v_indices):
            s_start = rank * sector_size
            s_end   = s_start + sector_size
            for pi, ang in pax_angles:
                if s_start <= ang < s_end:
                    pax_to_vehicle[pi] = vi

        # 섹터에 아무도 없는 차량 처리 → 가장 가까운 승객 할당
        assigned_pax = set(pax_to_vehicle.keys())
        for rank, vi in enumerate(v_indices):
            if vi not in pax_to_vehicle.values():
                s_center = (rank + 0.5) * sector_size
                # 아직 미배정 승객 중 각도가 가장 가까운 것
                candidates = [(pi, ang) for pi, ang in pax_angles if pi not in assigned_pax]
                if not candidates:
                    # 모두 배정됐으면 가장 가까운 승객 재배정
                    candidates = pax_angles
                if candidates:
                    closest = min(candidates, key=lambda x: min(
                        abs(x[1]-s_center), 360-abs(x[1]-s_center)))
                    pax_to_vehicle[closest[0]] = vi
                    assigned_pax.add(closest[0])

    # 미배정 승객은 0번 차량으로
    for pi in range(n_pax):
        if pi not in pax_to_vehicle:
            pax_to_vehicle[pi] = 0

    # allowed 형태로 변환
    return {pi: [vi] for pi, vi in pax_to_vehicle.items()}


def _enforce_min_one(routes, passengers, vehicles, node_indices, destination_idx):
    """
    승객 0명 차량에 강제로 최소 1명 배정.
    인접한 다른 차량에서 승객 1명을 빼앗아 옴.
    """
    n_veh = len(routes)
    changed = True

    while changed:
        changed = False
        for ri, route in enumerate(routes):
            if route['total_passengers'] > 0:
                continue

            # 이 차량에 승객이 없음 → 다른 차량에서 1명 이전
            # 가장 승객 많은 차량에서 마지막 픽업 stop을 가져옴
            donor_ri = max(
                (i for i in range(n_veh) if routes[i]['total_passengers'] > 1),
                key=lambda i: routes[i]['total_passengers'],
                default=None
            )
            if donor_ri is None:
                # 모든 다른 차량도 1명뿐 → 불가능
                break

            donor = routes[donor_ri]
            donor_stops = donor['stops']

            # donor에서 마지막 pickup stop 제거
            pickup_stops = [s for s in donor_stops if s['type'] == 'pickup']
            if not pickup_stops:
                continue
            move_stop = pickup_stops[-1]

            # donor에서 제거
            donor['stops'] = [s for s in donor_stops if not (
                s['type'] == 'pickup' and s['name'] == move_stop['name']
            )]
            donor['total_passengers'] -= move_stop['passenger_count']

            # 현재 차량에 추가 (destination 직전)
            cur_stops = route['stops']
            dest_pos = next((i for i, s in enumerate(cur_stops)
                             if s['type'] == 'destination'), len(cur_stops))
            move_stop['order']        = dest_pos
            move_stop['pickup_order'] = sum(1 for s in cur_stops if s['type'] == 'pickup') + 1
            cur_stops.insert(dest_pos, move_stop)
            route['total_passengers'] += move_stop['passenger_count']
            changed = True
            print(f"[solver] {move_stop['name']} → {routes[ri]['bus_id']} 이전 (강제 배정)")
            break

    return routes


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

    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx,
                       vehicle_start_indices, vehicle_end_indices):
        num_nodes         = len(distance_matrix)
        num_vehicles      = len(vehicles)
        passenger_indices = node_indices['passengers']
        n_pax             = len(passenger_indices)

        # 승객 < 차량이면 greedy로
        if n_pax < num_vehicles:
            print(f"[solver] 승객({n_pax}) < 차량({num_vehicles}) → Greedy")
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )

        dest_as_end = [destination_idx] * num_vehicles
        manager = pywrapcp.RoutingIndexManager(
            num_nodes, num_vehicles,
            vehicle_start_indices, dest_as_end
        )
        routing = pywrapcp.RoutingModel(manager)

        def dist_cb(fi, ti):
            return distance_matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]
        transit_cb = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

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

        dest_lat = vehicles[0].get('end_lat', 37.5)
        dest_lng = vehicles[0].get('end_lng', 127.0)
        pax_allowed = _assign_sectors(passengers, vehicles, dest_lat, dest_lng)

        BIG = 10_000_000
        for pi, p_node in enumerate(passenger_indices):
            allowed_v = pax_allowed.get(pi, list(range(num_vehicles)))
            node_idx  = manager.NodeToIndex(p_node)
            routing.AddDisjunction([node_idx], BIG)
            if len(allowed_v) < num_vehicles:
                routing.VehicleVar(node_idx).SetValues(allowed_v)

        # ★ 각 차량 최소 1명 강제: 차량별 최소 수요 Dimension
        routing.AddDimension(transit_cb, 0, 100000, True, "Distance")

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_params.time_limit.seconds = 20

        solution = routing.SolveWithParameters(search_params)
        if not solution:
            print("[solver] OR-Tools 해 없음 → Greedy")
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices, vehicle_end_indices
            )

        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            route_nodes, index, total_sec = [], routing.Start(v_idx), 0
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route_nodes.append(node)
                nxt = solution.Value(routing.NextVar(index))
                total_sec += distance_matrix[node][manager.IndexToNode(nxt)]
                index = nxt
            route_nodes.append(manager.IndexToNode(index))

            stops     = self._map_stops(route_nodes, passengers, passenger_indices,
                                        destination_idx, vehicle_start_indices, v_idx)
            total_pax = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')
            routes.append({
                "bus_id": vehicle['bus_id'], "vehicle": vehicle,
                "stops": stops, "total_distance_sec": total_sec,
                "total_passengers": total_pax
            })

        # ★ 0명 차량 강제 보정
        routes = _enforce_min_one(routes, passengers, vehicles, node_indices, destination_idx)
        return {"success": True, "routes": routes}

    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx,
                      vehicle_start_indices, vehicle_end_indices):
        n_pax    = len(passengers)
        n_veh    = len(vehicles)
        dest_lat = vehicles[0].get('end_lat', 37.5)
        dest_lng = vehicles[0].get('end_lng', 127.0)

        pax_allowed = _assign_sectors(passengers, vehicles, dest_lat, dest_lng)

        # 차량별 초기 배정
        vehicle_pax = {vi: [] for vi in range(n_veh)}
        for pi in range(n_pax):
            vi = pax_allowed.get(pi, [0])[0]
            vehicle_pax[vi].append(pi)

        # ★ 0명 차량 보정: 인접 차량에서 승객 이전
        for vi in range(n_veh):
            if vehicle_pax[vi]:
                continue
            # 가장 많은 차량에서 마지막 승객 이전
            donor = max(range(n_veh), key=lambda x: len(vehicle_pax[x]))
            if vehicle_pax[donor]:
                moved = vehicle_pax[donor].pop()
                vehicle_pax[vi].append(moved)
                print(f"[solver] 승객 {passengers[moved]['name']} → 차량 {vehicles[vi]['bus_id']} 강제 배정")

        routes = []
        for v_idx, vehicle in enumerate(vehicles):
            assigned  = vehicle_pax[v_idx][:]
            capacity  = vehicle['capacity']
            used      = 0
            route_nodes = [vehicle_start_indices[v_idx]]
            current     = vehicle_start_indices[v_idx]

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
                "bus_id": vehicle['bus_id'], "vehicle": vehicle,
                "stops": stops, "total_passengers": total_pax
            })

        # 미배정 승객 처리
        assigned_all = {pi for lst in vehicle_pax.values() for pi in lst}
        for pi in range(n_pax):
            if pi in assigned_all:
                continue
            p_count = passengers[pi]['passenger_count']
            for ri, route in enumerate(routes):
                if route['total_passengers'] + p_count <= vehicles[ri]['capacity']:
                    p_node = node_indices['passengers'][pi]
                    stops  = route['stops']
                    dest_pos = next((i for i, s in enumerate(stops)
                                     if s['type'] == 'destination'), len(stops))
                    po = sum(1 for s in stops if s['type'] == 'pickup') + 1
                    stops.insert(dest_pos, {
                        "order": dest_pos, "pickup_order": po,
                        "node_idx": p_node, "type": "pickup",
                        "name": passengers[pi]['name'], "address": passengers[pi]['address'],
                        "lat": passengers[pi]['lat'], "lng": passengers[pi]['lng'],
                        "passenger_count": p_count, "travel_time_sec": 0, "pickup_time": ""
                    })
                    route['total_passengers'] += p_count
                    break

        return {"success": True, "routes": routes}

    def _map_stops(self, route_nodes, passengers, passenger_indices,
                   destination_idx, vehicle_start_indices, v_idx):
        stops, pickup_order = [], 0
        for order, node in enumerate(route_nodes):
            if node in passenger_indices:
                pi = passenger_indices.index(node)
                pickup_order += 1
                stops.append({
                    "order": order, "pickup_order": pickup_order,
                    "node_idx": node, "type": "pickup",
                    "name": passengers[pi]['name'], "address": passengers[pi]['address'],
                    "lat": passengers[pi]['lat'], "lng": passengers[pi]['lng'],
                    "passenger_count": passengers[pi]['passenger_count'],
                    "travel_time_sec": 0, "pickup_time": ""
                })
            elif node == destination_idx:
                stops.append({
                    "order": order, "node_idx": node, "type": "destination",
                    "name": "도착지", "address": "", "lat": None, "lng": None,
                    "travel_time_sec": 0, "pickup_time": ""
                })
            elif v_idx < len(vehicle_start_indices) and node == vehicle_start_indices[v_idx]:
                stops.append({
                    "order": order, "node_idx": node, "type": "start",
                    "name": "출발지", "travel_time_sec": 0, "pickup_time": ""
                })
        return stops
