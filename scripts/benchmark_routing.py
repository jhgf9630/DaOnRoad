"""Repeatable synthetic metro benchmark; does not call address/road providers."""
import argparse
import json
import math
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from routing.matrix_builder import MatrixBuilder
from routing.haversine import build_haversine_matrix
from solver.vrp_solver import VRPSolver, RoutingError


def scenario(count=500, seed=42, spread=1.0):
    rng = random.Random(seed)
    destination = {'lat': 37.50, 'lng': 127.02}
    passengers = []
    # Dispersed within an approximately 60 x 50 km metro area. Synthetic,
    # without a claim that these positions are real pickup points or roads.
    for i in range(count):
        passengers.append(dict(name=f'Student{i+1}',address=f'Synthetic-{i+1}',passenger_count=1,
                               lat=37.50+spread*rng.uniform(-.25,.25),lng=127.02+spread*rng.uniform(-.32,.32)))
    capacities = [21]*10+[35]*5+[45]*5
    vehicles=[]
    for i,cap in enumerate(capacities):
        angle=2*math.pi*i/len(capacities)
        vehicles.append(dict(bus_id=f'Bus{i+1}',capacity=cap,start_location=f'Depot{i+1}',
                             start_lat=37.50+spread*.23*math.sin(angle),start_lng=127.02+spread*.29*math.cos(angle)))
    builder=MatrixBuilder()
    nodes,indices,dest,starts,ends=builder._build_nodes(passengers,vehicles,destination)
    matrix=build_haversine_matrix(nodes)
    # Directional variation exercises asymmetric travel costs.
    matrix=[[math.ceil(t*(1.08 if nodes[i]['lng']<nodes[j]['lng'] else 1)) for j,t in enumerate(row)] for i,row in enumerate(matrix)]
    return passengers,vehicles,matrix,indices,dest,starts,ends


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--students',type=int,default=500)
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--boarding',type=int,default=120)
    parser.add_argument('--output')
    parser.add_argument('--spread',type=float,default=1.0)
    args=parser.parse_args()
    began=time.monotonic()
    p,v,m,indices,d,s,e=scenario(args.students,spread=args.spread)
    try:
        result=VRPSolver().solve(m,p,v,indices,d,s,e,dict(search_seconds=args.seconds,boarding_sec=args.boarding))
        routes=result['routes']
        summary=dict(status='feasible',students=sum(r['total_passengers'] for r in routes),
            used_buses=len(routes),max_ride_min=max(r['max_ride_min'] for r in routes),
            average_ride_min=round(sum(r['passenger_time_sec'] for r in routes)/len(p)/60,2),
            total_vehicle_min=round(sum(r['total_duration_sec'] for r in routes)/60,2),
            capacity_violations=sum(r['total_passengers']>r['vehicle']['capacity'] for r in routes),
            duplicate_or_missing=len(p)!=len({s['node_idx'] for r in routes for s in r['stops'] if s['type']=='pickup'}),
            optimization=result['optimization'])
    except RoutingError as error:
        summary=error.as_dict()
    summary.update(scenario='synthetic asymmetric metro; not real OSRM',requested_students=args.students,
                   boarding_sec=args.boarding,spread=args.spread,wall_seconds=round(time.monotonic()-began,2))
    text=json.dumps(summary,ensure_ascii=False,indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
