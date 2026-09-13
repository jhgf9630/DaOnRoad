"""Old/new solver comparison on the same synthetic directed time matrix."""
import json
from pathlib import Path
import subprocess
import sys

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'backend')]
from benchmark_routing import scenario
from solver.vrp_solver import VRPSolver, route_metrics


def evaluate(result,p,m):
    pmap=dict(enumerate(p))
    passenger_nodes=[]
    rides,person_sec,duration,over= [],0,0,0
    for route in result['routes']:
        path=[s['node_idx'] for s in route['stops']]
        metric=route_metrics(path,m,pmap,120)
        passenger_nodes.extend(n for n in path if n in pmap)
        rides.extend(metric['rides'].values())
        person_sec+=metric['person_sec'];duration+=metric['duration_sec']
        over+=route['total_passengers']>route['vehicle']['capacity']
    return dict(assigned_groups=len(passenger_nodes),unique_groups=len(set(passenger_nodes)),
                used_buses=len(result['routes']),max_ride_min=round(max(rides)/60,2),
                average_ride_min=round(person_sec/len(p)/60,2),
                total_vehicle_min=round(duration/60,2),over_90_min_groups=sum(t>5400 for t in rides),
                capacity_violations=over)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p,v,m,indices,d,s,e=scenario(500,spread=.15)
    namespace={'__name__':'legacy_solver'}
    source=subprocess.check_output(['git','show','0752de5:backend/solver/vrp_solver.py'],cwd=root).decode('utf-8')
    exec(compile(source,'legacy_solver','exec'),namespace)
    old=namespace['VRPSolver']().solve(m,p,v,indices,d,s,e)
    new=VRPSolver().solve(m,p,v,indices,d,s,e,{'search_seconds':20})
    report=dict(scenario='500 synthetic pickups; compact spread .15; same matrix; 120 sec boarding; 20-second search',
                caveat='Not real metro roads. Legacy solver is evaluated on the corrected node layout.',
                old=evaluate(old,p,m),new=evaluate(new,p,m))
    output=json.dumps(report,ensure_ascii=False,indent=2)
    print(output)
    (root/'docs'/'solver-comparison.json').write_text(output+'\n',encoding='utf-8')
