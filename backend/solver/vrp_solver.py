"""Mandatory school transport VRP: bus cost + person-time, with hard limits.

Search travels backwards from the common destination to each depot. Cumulative
time at each pickup is exactly its forward boarding-to-destination time.
Soft upper bounds price that person-time; directed road costs are transposed. Every pickup is mandatory; no destructive reassignment fallback.
"""
from collections import Counter
import math
import time

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
except ImportError:
    pywrapcp = None


class RoutingError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details

    def as_dict(self):
        return {'code': self.code, 'message': str(self), **self.details}


DEFAULT_OPTIONS = dict(boarding_sec=120, max_ride_min=90, max_route_min=240,
                       vehicle_fixed_cost_min=30, passenger_time_weight=0.2,
                       use_all_vehicles=False, search_seconds=60)


def route_metrics(nodes, matrix, pmap, boarding_sec):
    driving = sum(matrix[a][b] for a, b in zip(nodes, nodes[1:]))
    remaining, rides = 0, {}
    for a, b in reversed(list(zip(nodes, nodes[1:]))):
        remaining += matrix[a][b]
        if a in pmap:
            remaining += boarding_sec
            rides[a] = remaining
    return dict(driving_sec=driving, duration_sec=remaining, rides=rides,
                person_sec=sum(rides[n] * pmap[n]['passenger_count'] for n in rides))


class VRPSolver:
    def solve(self, distance_matrix, passengers, vehicles, node_indices,
              destination_idx, vehicle_start_indices, vehicle_end_indices=None,
              options=None):
        opt = {**DEFAULT_OPTIONS, **(options or {})}
        pmap = dict(zip(node_indices['passengers'], passengers))
        self._validate_input(distance_matrix, passengers, vehicles, pmap,
                             destination_idx, vehicle_start_indices, opt)
        if pywrapcp is None:
            raise RoutingError('solver_unavailable', '배차 엔진이 없습니다. 백엔드를 다시 빌드해주세요.')
        began = time.monotonic()
        seed = self._sweep_seed(distance_matrix, vehicles, pmap, destination_idx,
                               vehicle_start_indices, opt, began + min(10, opt['search_seconds'] / 4))
        if seed is None:
            seed = self._insertion_seed(distance_matrix, vehicles, pmap, destination_idx,
                                       vehicle_start_indices, opt, began + min(12, opt['search_seconds'] / 3))
        repair_seed = seed
        if seed is None:
            repair_seed = self._sweep_seed(distance_matrix, vehicles, pmap, destination_idx,
                vehicle_start_indices, opt, began + min(15, opt['search_seconds'] / 3), allow_infeasible=True)
        strategies = [routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
                      routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION]
        candidates, statuses = [], []
        reference_attempt = None
        if seed is not None:
            self._validate_result(seed, distance_matrix, vehicles, pmap,
                                  destination_idx, vehicle_start_indices, opt)
            candidates.append(seed)
        for i, strategy in enumerate(strategies):
            remaining = opt['search_seconds'] - (time.monotonic() - began)
            if remaining < .05:
                break
            candidate, status = self._search(distance_matrix, vehicles, pmap,
                destination_idx, vehicle_start_indices, opt, strategy,
                remaining / (len(strategies) - i), relax_ride=(i == 1), seed=seed if i == 0 else repair_seed)
            statuses.append(status)
            if candidate is not None:
                try:
                    self._validate_result(candidate, distance_matrix, vehicles, pmap,
                                          destination_idx, vehicle_start_indices, opt)
                except RoutingError:
                    if i == 0: raise
                    rides = [t for _,path in candidate['paths'] for t in route_metrics(path,distance_matrix,pmap,opt['boarding_sec'])['rides'].values()]
                    reference_attempt = {'not_a_dispatch_plan': True, 'max_ride_min': round(max(rides)/60,1), 'over_limit_groups': sum(t>round(opt['max_ride_min']*60) for t in rides)}
                    continue
                candidates.append(candidate)
        if not candidates:
            raise RoutingError('no_feasible_solution',
                '제한 시간 안에 모든 학생을 정원·탑승시간 조건에 맞춰 배정하지 못했습니다. '
                '탐색 시간을 늘리거나 차량·시간 제한을 조정해주세요. 불가능함이 증명된 것은 아닙니다.',
                solver_statuses=statuses, reference_attempt=reference_attempt)
        best = min(candidates, key=lambda c: c['objective'])
        routes = []
        for vi, nodes in best['paths']:
            vehicle = vehicles[vi]
            metrics = route_metrics(nodes, distance_matrix, pmap, opt['boarding_sec'])
            stops, pickup_order = [], 0
            for order, node in enumerate(nodes):
                stop = dict(order=order, node_idx=node, travel_time_sec=0)
                if node in pmap:
                    pickup_order += 1
                    stop.update(pmap[node], type='pickup', pickup_order=pickup_order,
                                ride_time_sec=metrics['rides'][node],
                                ride_time_min=round(metrics['rides'][node] / 60, 1))
                elif node == destination_idx:
                    stop.update(type='destination', name='도착지')
                else:
                    stop.update(type='start', name='출발지', address=vehicle['start_location'],
                                lat=vehicle['start_lat'], lng=vehicle['start_lng'])
                if order < len(nodes) - 1:
                    stop['travel_time_sec'] = distance_matrix[node][nodes[order + 1]]
                stops.append(stop)
            total = sum(pmap[n]['passenger_count'] for n in nodes if n in pmap)
            routes.append(dict(bus_id=vehicle['bus_id'], vehicle=vehicle, stops=stops,
                total_passengers=total, driving_sec=metrics['driving_sec'],
                total_duration_sec=metrics['duration_sec'],
                max_ride_min=round(max(metrics['rides'].values()) / 60, 1),
                average_ride_min=round(metrics['person_sec'] / total / 60, 1),
                passenger_time_sec=metrics['person_sec']))
        used = {vi for vi, _ in best['paths']}
        return dict(success=True, routes=routes,
            unused_bus_ids=[v['bus_id'] for vi, v in enumerate(vehicles) if vi not in used],
            optimization=dict(status='feasible', optimality_proven=False,
                objective_score=best['objective'], elapsed_seconds=round(time.monotonic()-began, 2),
                candidates_found=len(candidates), options=opt, cost_unit='weighted_seconds_not_currency'))

    @staticmethod
    def _sweep_seed(matrix, vehicles, pmap, dest, starts, opt, deadline, allow_infeasible=False):
        # A geographic sweep supplies diverse spatially coherent initial routes;
        # actual directed road times decide ordering, limits, and final costs.
        # It is a seed only, not the optimization objective or a success bypass.
        if len(pmap) < len(vehicles):
            return None
        center_lat = sum(p['lat'] for p in pmap.values()) / len(pmap)
        center_lng = sum(p['lng'] for p in pmap.values()) / len(pmap)
        angle = lambda lat,lng: math.atan2(lat-center_lat, (lng-center_lng)*math.cos(math.radians(center_lat)))
        ordered = sorted(pmap, key=lambda n:angle(pmap[n]['lat'],pmap[n]['lng']))
        bus_order = sorted(range(len(vehicles)), key=lambda vi:angle(vehicles[vi]['start_lat'],vehicles[vi]['start_lng']))
        # Water-fill target loads: small buses fill first; big buses do not carry
        # 45 stops just because they have 45 seats when more buses are available.
        targets = [0]*len(vehicles)
        remaining = sum(p['passenger_count'] for p in pmap.values())
        while remaining:
            for vi in bus_order:
                if targets[vi] < vehicles[vi]['capacity'] and remaining:
                    targets[vi] += 1
                    remaining -= 1
        def score(path):
            metric=route_metrics(path,matrix,pmap,opt['boarding_sec'])
            over = sum(max(0,t-round(opt['max_ride_min']*60)) for t in metric['rides'].values()) if opt['max_ride_min'] is not None else 0
            return metric['duration_sec']*100+metric['person_sec']*round(opt['passenger_time_weight']*100)+over*10**7
        best=None
        for offset in range(8):
            if time.monotonic()>deadline: break
            shift=int(len(ordered)*offset/8)
            pending=ordered[shift:]+ordered[:shift]
            cursor,paths=0,[]
            for vi in bus_order:
                group,load=[],0
                while cursor<len(pending) and load<targets[vi]:
                    node=pending[cursor]
                    if load+pmap[node]['passenger_count']>vehicles[vi]['capacity']: break
                    group.append(node);load+=pmap[node]['passenger_count'];cursor+=1
                if not group: break
                # Nearest predecessor from the destination, then directed 2-opt.
                reverse,current=[],dest
                while group:
                    node=min(group,key=lambda n:matrix[n][current])
                    reverse.append(node);group.remove(node);current=node
                path=[starts[vi],*reversed(reverse),dest]
                value=score(path)
                for _ in range(4):
                    changed=False
                    for a in range(1,len(path)-2):
                        for b in range(a+2,len(path)):
                            if time.monotonic()>deadline: break
                            trial=path[:a]+list(reversed(path[a:b]))+path[b:]
                            trial_value=score(trial)
                            if trial_value<value:
                                path,value=trial,trial_value;changed=True
                    if not changed or time.monotonic()>deadline: break
                paths.append((vi,path))
            if cursor!=len(pending) or len(paths)!=len(vehicles): continue
            candidate={'paths':paths,'objective':sum(score(path)+round(opt['vehicle_fixed_cost_min']*60*100) for _,path in paths)}
            try:
                VRPSolver._validate_result(candidate,matrix,vehicles,pmap,dest,starts,{**opt,'max_ride_min':None} if allow_infeasible else opt)
            except RoutingError:
                continue
            if best is None or candidate['objective']<best['objective']: best=candidate
        return best

    @staticmethod
    def _insertion_seed(matrix, vehicles, pmap, dest, starts, opt, deadline):
        # Hardest (largest, farthest) groups first. Evaluate every feasible
        # insertion using directed road costs and all affected students' rides.
        paths = [[start, dest] for start in starts]
        loads = [0] * len(vehicles)
        scores = [0] * len(vehicles)
        order = sorted(pmap, key=lambda n: (pmap[n]['passenger_count'], matrix[n][dest]), reverse=True)
        for step,node in enumerate(order):
            best = None
            for vi, path in enumerate(paths):
                if opt['use_all_vehicles'] and len(order)-step == sum(load==0 for load in loads) and loads[vi]:
                    continue
                if loads[vi] + pmap[node]['passenger_count'] > vehicles[vi]['capacity']:
                    continue
                for position in range(1,len(path)):
                    if time.monotonic() > deadline:
                        return None
                    candidate = path[:position] + [node] + path[position:]
                    metric = route_metrics(candidate,matrix,pmap,opt['boarding_sec'])
                    if metric['duration_sec'] > round(opt['max_route_min']*60):
                        continue
                    if opt['max_ride_min'] is not None and max(metric['rides'].values()) > round(opt['max_ride_min']*60):
                        continue
                    score = (metric['duration_sec']*100 + round(opt['vehicle_fixed_cost_min']*60*100)
                             + metric['person_sec']*round(opt['passenger_time_weight']*100))
                    choice = (score-scores[vi],vi,position,score)
                    if best is None or choice < best:
                        best = choice
            if best is None:
                return None
            _,vi,position,score=best
            paths[vi].insert(position,node)
            scores[vi]=score
            loads[vi]+=pmap[node]['passenger_count']
        if opt['use_all_vehicles'] and any(load==0 for load in loads):
            return None
        return {'paths':[(vi,p) for vi,p in enumerate(paths) if loads[vi]],'objective':sum(scores)}

    @staticmethod
    def _validate_input(matrix, passengers, vehicles, pmap, dest, starts, opt):
        if not passengers or not vehicles:
            raise RoutingError('empty_input', '학생과 차량을 각각 1개 이상 입력해주세요.')
        if any(type(p['passenger_count']) is not int or p['passenger_count'] < 1 for p in passengers):
            raise RoutingError('invalid_count', '탑승 인원은 양의 정수여야 합니다.')
        if any(type(v['capacity']) is not int or v['capacity'] < 1 for v in vehicles):
            raise RoutingError('invalid_capacity', '차량 정원은 양의 정수여야 합니다.')
        if len({v['bus_id'] for v in vehicles}) != len(vehicles):
            raise RoutingError('duplicate_bus', '버스 ID가 중복됩니다.')
        n = len(matrix)
        if (n != len(passengers)+1+len(vehicles) or len(pmap) != len(passengers)
                or len(starts) != len(vehicles) or len(set(starts)) != len(starts)
                or set(pmap) | {dest} | set(starts) != set(range(n))):
            raise RoutingError('invalid_nodes', '노드 구성이 올바르지 않습니다.')
        if any(len(row) != n or any(type(x) is not int or x < 0 for x in row) for row in matrix):
            raise RoutingError('invalid_matrix', '이동시간 행렬이 올바르지 않습니다.')
        if sum(p['passenger_count'] for p in passengers) > sum(v['capacity'] for v in vehicles):
            raise RoutingError('insufficient_capacity', '전체 학생 수가 차량 정원 합계를 초과합니다.')
        oversized = [i for i,p in enumerate(passengers) if p['passenger_count'] > max(v['capacity'] for v in vehicles)]
        if oversized:
            raise RoutingError('group_too_large', '한 행의 인원이 최대 차량 정원보다 큽니다. 그룹은 분할하지 않습니다.', passenger_indices=oversized)
        if opt['use_all_vehicles'] and len(passengers) < len(vehicles):
            raise RoutingError('too_many_vehicles', '전체 차량 사용 시 학생 그룹 수가 차량 수 이상이어야 합니다.')
        if not 1 <= opt['search_seconds'] <= 180 or not 0 <= opt['boarding_sec'] <= 600:
            raise RoutingError('invalid_options', '탐색시간 또는 탑승 대기시간이 범위를 벗어났습니다.')
        if not 1 <= opt['max_route_min'] <= 1440 or (opt['max_ride_min'] is not None and not 1 <= opt['max_ride_min'] <= 1440):
            raise RoutingError('invalid_options', '운행·탑승시간 제한이 범위를 벗어났습니다.')
        if not math.isfinite(opt['passenger_time_weight']) or not 0 <= opt['passenger_time_weight'] <= 10 or not 0 <= opt['vehicle_fixed_cost_min'] <= 1440:
            raise RoutingError('invalid_options', '비용 가중치가 범위를 벗어났습니다.')

    @staticmethod
    def _search(matrix, vehicles, pmap, dest, starts, opt, strategy, seconds, relax_ride=False, seed=None):
        manager = pywrapcp.RoutingIndexManager(len(matrix), len(vehicles), [dest]*len(vehicles), starts)
        routing = pywrapcp.RoutingModel(manager)
        index_nodes = [manager.IndexToNode(i) for i in range(manager.GetNumberOfIndices())]
        # Native lookup tables avoid millions of Python callbacks at 500+ nodes.
        transit_matrix = [[matrix[b][a] + (opt['boarding_sec'] if b in pmap else 0)
                           for b in range(len(matrix))] for a in range(len(matrix))]
        for start in starts:
            transit_matrix[dest][start] = 0  # parked vehicle
        transit_id = routing.RegisterTransitMatrix(transit_matrix)
        cost_id = routing.RegisterTransitMatrix([[value*100 for value in row] for row in transit_matrix])
        routing.SetArcCostEvaluatorOfAllVehicles(cost_id)
        routing.SetFixedCostOfAllVehicles(round(opt['vehicle_fixed_cost_min']*60*100))
        demand_id = routing.RegisterUnaryTransitVector([pmap.get(n,{}).get('passenger_count',0) for n in range(len(matrix))])
        routing.AddDimensionWithVehicleCapacity(demand_id, 0, [v['capacity'] for v in vehicles], True, 'Capacity')
        horizon = round(opt['max_route_min']*60)
        routing.AddDimension(transit_id, 0, horizon, True, 'Time')
        dimension = routing.GetDimensionOrDie('Time')
        routing.AddDimension(transit_id, 0, horizon, True, 'PassengerTime')
        passenger_dimension = routing.GetDimensionOrDie('PassengerTime')
        for vi in range(len(vehicles)):
            if opt['use_all_vehicles']:
                routing.solver().Add(routing.NextVar(routing.Start(vi)) != routing.End(vi))
        for node, passenger in pmap.items():
            index = manager.NodeToIndex(node)
            if opt['max_ride_min'] is not None:
                if relax_ride:
                    # Repair search can traverse infeasible intermediate routes.
                    # Only independently verified, fully feasible results escape.
                    dimension.SetCumulVarSoftUpperBound(index,round(opt['max_ride_min']*60),10**7)
                else:
                    dimension.CumulVar(index).SetMax(min(horizon,round(opt['max_ride_min']*60)))
            weight = round(opt['passenger_time_weight']*100)*passenger['passenger_count']
            if weight:
                passenger_dimension.SetCumulVarSoftUpperBound(index,0,weight)
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = strategy
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromMilliseconds(max(1,int(seconds*1000)))
        initial = None
        if seed is not None:
            reverse_routes = [[] for _ in vehicles]
            for vi,path in seed['paths']:
                reverse_routes[vi] = list(reversed(path[1:-1]))
            initial = routing.ReadAssignmentFromRoutes(reverse_routes, True)
        solution = routing.SolveFromAssignmentWithParameters(initial, params) if initial else routing.SolveWithParameters(params)
        if solution is None:
            return None,routing.status()
        paths=[]
        for vi in range(len(vehicles)):
            if not routing.IsVehicleUsed(solution,vi):
                continue
            idx,path=routing.Start(vi),[]
            while not routing.IsEnd(idx):
                path.append(index_nodes[idx])
                idx=solution.Value(routing.NextVar(idx))
            path.append(starts[vi])
            paths.append((vi,list(reversed(path))))
        return dict(paths=paths,objective=solution.ObjectiveValue()),routing.status()

    @staticmethod
    def _validate_result(result,matrix,vehicles,pmap,dest,starts,opt):
        seen,used=[],set()
        for vi,path in result['paths']:
            if vi in used or path[0]!=starts[vi] or path[-1]!=dest or any(n not in pmap for n in path[1:-1]):
                raise RoutingError('invalid_solution','배차 검증 실패: 차량 또는 경로 구성 오류')
            used.add(vi)
            seen.extend(path[1:-1])
            if not path[1:-1] or sum(pmap[n]['passenger_count'] for n in path[1:-1])>vehicles[vi]['capacity']:
                raise RoutingError('invalid_solution','배차 검증 실패: 빈 차량 또는 정원 초과')
            metric=route_metrics(path,matrix,pmap,opt['boarding_sec'])
            if metric['duration_sec']>round(opt['max_route_min']*60) or (opt['max_ride_min'] is not None and max(metric['rides'].values())>round(opt['max_ride_min']*60)):
                raise RoutingError('invalid_solution','배차 검증 실패: 운행·탑승시간 초과')
        if Counter(seen)!=Counter({n:1 for n in pmap}) or (opt['use_all_vehicles'] and len(used)!=len(vehicles)):
            raise RoutingError('invalid_solution','배차 검증 실패: 누락·중복 또는 차량 사용 조건 위반')
