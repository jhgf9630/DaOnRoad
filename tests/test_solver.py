import itertools
import pytest
from routing.matrix_builder import MatrixBuilder
from scheduler.time_scheduler import TimeScheduler
from solver.vrp_solver import VRPSolver, RoutingError, route_metrics


def make_problem(counts=(1,1,1), capacities=(2,2)):
    p=[dict(name=f'p{i}',address=f'a{i}',passenger_count=c,lat=37+i*.01,lng=127.) for i,c in enumerate(counts)]
    v=[dict(bus_id=f'b{i}',capacity=c,start_location='depot',start_lat=37.,start_lng=127.) for i,c in enumerate(capacities)]
    n,idx,d,s,e=MatrixBuilder()._build_nodes(p,v,dict(lat=37.5,lng=127.))
    m=[[0 if i==j else 60+(i*73+j*41)%240 for j in range(len(n))] for i in range(len(n))]
    return p,v,m,idx,d,s,e


def solve(problem, **options):
    p,v,m,idx,d,s,e=problem
    return VRPSolver().solve(m,p,v,idx,d,s,e,{'search_seconds':1,**options})


def test_no_extra_destination_nodes():
    p,v,m,idx,d,s,e=make_problem()
    assert len(m)==len(p)+1+len(v)
    assert e==[d]*len(v)


def test_oversized_indivisible_group_is_error():
    with pytest.raises(RoutingError,match='분할'):
        solve(make_problem((6,),(5,5)))


def test_all_passengers_and_capacity():
    problem=make_problem((2,6),(10,2))
    result=solve(problem,use_all_vehicles=True)
    assert sorted(r['total_passengers'] for r in result['routes'])==[2,6]
    assert all(r['total_passengers']<=r['vehicle']['capacity'] for r in result['routes'])


def test_unused_vehicles_are_parked():
    result=solve(make_problem((1,),(5,5,5)))
    assert len(result['routes'])==1
    assert len(result['unused_bus_ids'])==2


def test_capacity_packing_failure_not_partial_success():
    with pytest.raises(RoutingError):
        solve(make_problem((4,4,4),(6,6)))


def test_hard_ride_limit():
    problem=make_problem((1,),(5,))
    problem[2][0][problem[4]]=6000
    with pytest.raises(RoutingError):
        solve(problem,max_ride_min=90)


def test_asymmetric_objective_matches_exhaustive_small_problem():
    problem=make_problem((1,2,1),(3,3))
    p,v,m,idx,d,starts,e=problem
    pmap=dict(enumerate(p))
    best=float('inf')
    # Enumerate every assignment and within-vehicle permutation (3 pickups).
    for assignment in itertools.product(range(2),repeat=3):
        groups=[[i for i,a in enumerate(assignment) if a==vi] for vi in range(2)]
        if any(sum(p[i]['passenger_count'] for i in group)>v[vi]['capacity'] for vi,group in enumerate(groups)):
            continue
        for perm in itertools.product(*(list(itertools.permutations(g)) for g in groups)):
            cost=0
            for vi,group in enumerate(perm):
                if not group: continue
                metrics=route_metrics([starts[vi],*group,d],m,pmap,120)
                cost+=metrics['duration_sec']*100+30*60*100+metrics['person_sec']*20
            best=min(best,cost)
    result=solve(problem)
    assert result['optimization']['objective_score']==best
    assert result['optimization']['optimality_proven'] is False


def test_validator_rejects_duplicate_and_omission():
    p,v,m,idx,d,starts,e=make_problem()
    from solver.vrp_solver import DEFAULT_OPTIONS
    with pytest.raises(RoutingError):
        VRPSolver._validate_result({'paths':[(0,[starts[0],0,0,d])]},m,v,dict(enumerate(p)),d,starts,DEFAULT_OPTIONS)


def test_real_departure_and_previous_day():
    problem=make_problem((1,),(5,))
    p,v,m,idx,d,starts,e=problem
    m[starts[0]][0]=600;m[0][d]=600
    routes=solve(problem)['routes']
    result=TimeScheduler().calculate_times(routes,'00:10',m,idx,p,v,d,service_date='2026-09-13')[0]
    assert result['departure_time']=='23:48'
    assert result['first_pickup_time']=='23:58'
    assert result['total_duration_min']==22
    assert result['departure_day_offset']==-1
    assert result['departure_datetime'].startswith('2026-09-12')
    assert result['stops'][1]['ride_time_sec']==720


def test_missing_engine_cannot_fall_back_to_unsafe_greedy(monkeypatch):
    import solver.vrp_solver as module
    monkeypatch.setattr(module,'pywrapcp',None)
    with pytest.raises(RoutingError,match='엔진'):
        solve(make_problem())
