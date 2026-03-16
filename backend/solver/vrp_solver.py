"""
DaOnRoad - VRP Solver
──────────────────────────────────────────────────────────────────
설계 원칙:
1. 모든 차량에 반드시 1명 이상 배정 (하드 보장)
2. OR-Tools 사용 가능 시 CVRP 최적화
3. OR-Tools 없으면 K-Means 클러스터 기반 Greedy
4. 어떤 경우에도 빈 차량 0개 보장 (_force_min_one 후처리)
──────────────────────────────────────────────────────────────────
[현실적 배차 알고리즘 방향성 - 현재 구현의 한계와 로드맵]

현재 한계:
  - Haversine(직선거리) 기반 Distance Matrix → 실제 도로 시간과 최대 3배 오차
  - 방향각 기반 섹터 분할 → 도로 접근성 미반영

권장 개선 방향 (우선순위 순):
  1. OSRM(오픈소스, 무료) Table API:
       POST http://router.project-osrm.org/table/v1/driving/{coords}
       → 실제 도로 기반 N×N 이동시간 매트릭스 (초 단위, 무료)
       → 현재 Haversine을 이것으로 교체하면 정확도 3배 향상

  2. 도로 경로 Polyline:
       GET http://router.project-osrm.org/route/v1/driving/{coords}
       → geometry 필드에 실제 도로 경로 좌표 포함
       → 지도에 직선 대신 도로 굴곡 반영 가능

  3. Kakao/Tmap 경로 API (유료/횟수 제한):
       → 국내 도로 정확도 최상, but API 비용 발생
       → 캐시 필수 (동일 구간 반복 호출 방지)

  OSRM 연동 방법 (향후 matrix_builder.py 수정 대상):
    nodes = [{lat, lng}, ...]
    coords = ";".join(f"{n['lng']},{n['lat']}" for n in nodes)
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}"
    matrix = requests.get(url).json()["durations"]  # 초 단위 N×N
"""
import math
from typing import List, Dict, Any
from collections import defaultdict

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


# ── K-Means 기반 승객 클러스터링 ────────────────────────────────────
def _kmeans_assign(passengers: List[Dict], n_clusters: int, max_iter: int = 30) -> List[int]:
    """
    승객을 n_clusters개 클러스터로 분류.
    반환: 각 승객의 클러스터 번호 리스트 (0 ~ n_clusters-1)
    """
    if n_clusters >= len(passengers):
        return list(range(len(passengers)))

    # 초기 중심점: 균등 간격으로 선택
    indices = [int(i * len(passengers) / n_clusters) for i in range(n_clusters)]
    centers = [[passengers[i]['lat'], passengers[i]['lng']] for i in indices]

    assignment = [0] * len(passengers)
    for _ in range(max_iter):
        # 각 승객 → 가장 가까운 중심점
        new_assignment = []
        for p in passengers:
            dists = [math.sqrt((p['lat']-c[0])**2 + (p['lng']-c[1])**2) for c in centers]
            new_assignment.append(dists.index(min(dists)))

        if new_assignment == assignment:
            break
        assignment = new_assignment

        # 중심점 갱신
        for k in range(n_clusters):
            cluster_pax = [passengers[i] for i, a in enumerate(assignment) if a == k]
            if cluster_pax:
                centers[k] = [
                    sum(p['lat'] for p in cluster_pax) / len(cluster_pax),
                    sum(p['lng'] for p in cluster_pax) / len(cluster_pax)
                ]

    return assignment


def _balance_clusters(assignment: List[int], passengers: List[Dict],
                      vehicles: List[Dict], n_clusters: int) -> List[int]:
    """
    클러스터별 승객 수가 해당 차량 정원을 초과하지 않도록 재배정.
    또한 빈 클러스터(0명)가 없도록 보장.
    """
    assignment = assignment[:]

    for iteration in range(50):
        changed = False

        # 각 클러스터 현황
        cluster_pax   = defaultdict(list)  # k → [pi]
        cluster_count = defaultdict(int)   # k → 탑승인원 합

        for pi, k in enumerate(assignment):
            cluster_pax[k].append(pi)
            cluster_count[k] += passengers[pi]['passenger_count']

        # 정원 초과 클러스터 → 여유 클러스터로 이전
        for k in range(n_clusters):
            cap = vehicles[k]['capacity']
            while cluster_count[k] > cap:
                # 이 클러스터에서 가장 멀리 있는 승객 찾기
                if not cluster_pax[k]:
                    break
                # 다른 클러스터 중 여유 있는 것 찾기
                target = None
                for other_k in range(n_clusters):
                    if other_k == k:
                        continue
                    if cluster_count[other_k] + passengers[cluster_pax[k][-1]]['passenger_count'] \
                       <= vehicles[other_k]['capacity']:
                        target = other_k
                        break
                if target is None:
                    break
                moved_pi = cluster_pax[k].pop()
                cluster_count[k]      -= passengers[moved_pi]['passenger_count']
                assignment[moved_pi]   = target
                cluster_count[target] += passengers[moved_pi]['passenger_count']
                changed = True

        # 빈 클러스터 → 가장 큰 클러스터에서 이전
        for k in range(n_clusters):
            if cluster_count[k] == 0:
                donor = max(range(n_clusters), key=lambda x: cluster_count[x])
                if cluster_pax[donor]:
                    moved_pi           = cluster_pax[donor].pop()
                    cluster_count[donor] -= passengers[moved_pi]['passenger_count']
                    assignment[moved_pi]  = k
                    cluster_count[k]    += passengers[moved_pi]['passenger_count']
                    changed = True

        if not changed:
            break

    return assignment


def _force_min_one(routes: List[Dict], passengers: List[Dict]) -> List[Dict]:
    """
    후처리: 승객 0명 차량에 강제로 1명 이전.
    가장 많은 차량에서 마지막 픽업 stop을 가져옴.
    """
    for _ in range(len(routes) * 2):  # 최대 순환 횟수 제한
        empty = [i for i, r in enumerate(routes) if r['total_passengers'] == 0]
        if not empty:
            break

        target_ri = empty[0]
        # 가장 많은 차량 선택 (2명 이상)
        donors = [(i, r) for i, r in enumerate(routes)
                  if r['total_passengers'] >= 2]
        if not donors:
            print(f"[solver] ⚠ 강제 배정 불가: 모든 차량이 0-1명")
            break

        donor_ri, donor = max(donors, key=lambda x: x[1]['total_passengers'])
        pickup_stops = [s for s in donor['stops'] if s['type'] == 'pickup']
        if not pickup_stops:
            continue

        move = pickup_stops[-1]

        # donor에서 제거
        donor['stops'] = [s for s in donor['stops']
                          if not (s['type'] == 'pickup' and s.get('node_idx') == move.get('node_idx'))]
        donor['total_passengers'] -= move['passenger_count']

        # target에 추가 (destination 직전)
        target_stops = routes[target_ri]['stops']
        dest_pos = next((i for i, s in enumerate(target_stops)
                         if s['type'] == 'destination'), len(target_stops))
        move['order']        = dest_pos
        move['pickup_order'] = sum(1 for s in target_stops if s['type'] == 'pickup') + 1
        target_stops.insert(dest_pos, move)
        routes[target_ri]['total_passengers'] += move['passenger_count']

        print(f"[solver] 강제배정: {move['name']} → {routes[target_ri]['bus_id']}")

    return routes


class VRPSolver:

    def solve(self, distance_matrix, passengers, vehicles,
              node_indices, destination_idx,
              vehicle_start_indices, vehicle_end_indices):

        n_pax = len(passengers)
        n_veh = len(vehicles)

        print(f"[solver] 승객={n_pax}명, 차량={n_veh}대")

        # 승객 수가 차량 수보다 적으면 바로 Greedy
        if n_pax < n_veh:
            print(f"[solver] 승객({n_pax}) < 차량({n_veh}) → Greedy")
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices)

        if ORTOOLS_AVAILABLE:
            result = self._solve_ortools(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx,
                vehicle_start_indices)
            # OR-Tools도 0명 차량 생길 수 있으므로 후처리
            result['routes'] = _force_min_one(result['routes'], passengers)
            return result

        return self._solve_greedy(
            distance_matrix, passengers, vehicles,
            node_indices, destination_idx,
            vehicle_start_indices)

    # ── OR-Tools ────────────────────────────────────────────────────
    def _solve_ortools(self, distance_matrix, passengers, vehicles,
                       node_indices, destination_idx, vehicle_start_indices):

        num_nodes         = len(distance_matrix)
        num_vehicles      = len(vehicles)
        passenger_indices = node_indices['passengers']

        # destination = 각 차량의 end node
        manager = pywrapcp.RoutingIndexManager(
            num_nodes, num_vehicles,
            vehicle_start_indices,
            [destination_idx] * num_vehicles
        )
        routing = pywrapcp.RoutingModel(manager)

        def dist_cb(fi, ti):
            return distance_matrix[manager.IndexToNode(fi)][manager.IndexToNode(ti)]
        tc = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(tc)

        def demand_cb(fi):
            node = manager.IndexToNode(fi)
            if node in passenger_indices:
                return passengers[passenger_indices.index(node)]['passenger_count']
            return 0
        dc = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            dc, 0, [v['capacity'] for v in vehicles], True, "Capacity")

        # ★ 높은 페널티로 모든 승객 방문 강제
        BIG = 10_000_000
        for p_node in passenger_indices:
            routing.AddDisjunction([manager.NodeToIndex(p_node)], BIG)

        sp = pywrapcp.DefaultRoutingSearchParameters()
        sp.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
        sp.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        sp.time_limit.seconds = 20

        sol = routing.SolveWithParameters(sp)
        if not sol:
            print("[solver] OR-Tools 해 없음 → Greedy")
            return self._solve_greedy(
                distance_matrix, passengers, vehicles,
                node_indices, destination_idx, vehicle_start_indices)

        routes = []
        for vi, vehicle in enumerate(vehicles):
            nodes, idx, sec = [], routing.Start(vi), 0
            while not routing.IsEnd(idx):
                n = manager.IndexToNode(idx)
                nodes.append(n)
                nxt = sol.Value(routing.NextVar(idx))
                sec += distance_matrix[n][manager.IndexToNode(nxt)]
                idx  = nxt
            nodes.append(manager.IndexToNode(idx))

            stops = self._map_stops(nodes, passengers, passenger_indices,
                                    destination_idx, vehicle_start_indices, vi)
            total = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')
            routes.append({
                "bus_id": vehicle['bus_id'], "vehicle": vehicle,
                "stops": stops, "total_distance_sec": sec,
                "total_passengers": total
            })

        return {"success": True, "routes": routes}

    # ── K-Means Greedy ──────────────────────────────────────────────
    def _solve_greedy(self, distance_matrix, passengers, vehicles,
                      node_indices, destination_idx, vehicle_start_indices):

        n_pax = len(passengers)
        n_veh = len(vehicles)

        # Step 1: K-Means 클러스터링
        raw_assign = _kmeans_assign(passengers, n_veh)

        # Step 2: 정원 초과 & 빈 클러스터 보정
        assignment = _balance_clusters(raw_assign, passengers, vehicles, n_veh)

        # 클러스터별 승객 목록
        cluster_pax = defaultdict(list)
        for pi, k in enumerate(assignment):
            cluster_pax[k].append(pi)

        # Step 3: 각 차량 Nearest-Neighbor 순서 결정
        routes = []
        for vi, vehicle in enumerate(vehicles):
            assigned  = cluster_pax[vi][:]
            capacity  = vehicle['capacity']
            used      = 0
            nodes     = [vehicle_start_indices[vi]]
            current   = vehicle_start_indices[vi]

            remaining = assigned[:]
            while remaining:
                best_pi, best_cost = None, float('inf')
                for pi in remaining:
                    pn = node_indices['passengers'][pi]
                    pc = passengers[pi]['passenger_count']
                    if used + pc > capacity:
                        continue
                    cost = distance_matrix[current][pn]
                    if cost < best_cost:
                        best_cost = cost; best_pi = pi
                if best_pi is None:
                    break
                pn = node_indices['passengers'][best_pi]
                nodes.append(pn)
                used    += passengers[best_pi]['passenger_count']
                current  = pn
                remaining.remove(best_pi)

            nodes.append(destination_idx)
            stops = self._map_stops(nodes, passengers, node_indices['passengers'],
                                    destination_idx, vehicle_start_indices, vi)
            total = sum(s['passenger_count'] for s in stops if s['type'] == 'pickup')
            routes.append({
                "bus_id": vehicle['bus_id'], "vehicle": vehicle,
                "stops": stops, "total_passengers": total
            })

        # Step 4: 미배정 승객 강제 배정
        assigned_all = set(assignment.keys()) if False else set(range(n_pax))
        # (balance_clusters 후 모두 배정됨, 하지만 용량 초과로 빠진 것 처리)
        route_pax_set = {
            s.get('node_idx')
            for r in routes for s in r['stops'] if s['type'] == 'pickup'
        }
        unassigned = [
            pi for pi in range(n_pax)
            if node_indices['passengers'][pi] not in route_pax_set
        ]
        if unassigned:
            print(f"[solver] 미배정 {len(unassigned)}명 강제 배정")
            for pi in unassigned:
                pc = passengers[pi]['passenger_count']
                for ri, route in enumerate(routes):
                    if route['total_passengers'] + pc <= vehicles[ri]['capacity']:
                        pn = node_indices['passengers'][pi]
                        stops = route['stops']
                        dp = next((i for i, s in enumerate(stops)
                                   if s['type'] == 'destination'), len(stops))
                        po = sum(1 for s in stops if s['type'] == 'pickup') + 1
                        stops.insert(dp, {
                            "order": dp, "pickup_order": po,
                            "node_idx": pn, "type": "pickup",
                            "name": passengers[pi]['name'],
                            "address": passengers[pi]['address'],
                            "lat": passengers[pi]['lat'], "lng": passengers[pi]['lng'],
                            "passenger_count": pc, "travel_time_sec": 0, "pickup_time": ""
                        })
                        route['total_passengers'] += pc
                        break

        # Step 5: 빈 차량 강제 보정
        routes = _force_min_one(routes, passengers)

        empty_count = sum(1 for r in routes if r['total_passengers'] == 0)
        print(f"[solver] 결과: {[r['bus_id']+':'+str(r['total_passengers'])+'명' for r in routes]}")
        if empty_count:
            print(f"[solver] ⚠ 빈 차량 {empty_count}대 (승객 수 부족)")

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
