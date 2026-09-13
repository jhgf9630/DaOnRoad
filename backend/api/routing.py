"""Routing pipeline, with live progress and independently verified output."""
import os
from fastapi import APIRouter, HTTPException
from api.models import RouteRequest, Passenger, VehicleConfig, SearchRequest
from routing.matrix_builder import MatrixBuilder
from routing.geocoder import Geocoder
from routing.distance_cache import DistanceCache
from routing.osrm_service import check_osrm_health
from solver.vrp_solver import VRPSolver, RoutingError
from scheduler.time_scheduler import TimeScheduler

router = APIRouter()
geocoder = Geocoder()


@router.post('/search-address')
def search_address(body: SearchRequest):
    if not (os.environ.get('KAKAO_API_KEY') or os.environ.get('TMAP_API_KEY')):
        raise HTTPException(503, '주소 검색 키가 설정되지 않았습니다.')
    results = geocoder.search(body.query, limit=body.limit)
    return {'results': results, 'count': len(results)}


@router.post('/geocode')
def geocode_address(body: dict[str, str]):
    address = body.get('address', '').strip()
    if not address:
        raise HTTPException(400, '주소를 입력해주세요.')
    results = geocoder.search(address, limit=1)
    if not results:
        raise HTTPException(404, '주소를 찾을 수 없습니다. 주소를 수정해주세요.')
    return results[0]


def calculate_route(request: RouteRequest, progress=lambda *a: None):
    progress('addresses', 2, '출발지와 도착지 확인')
    if request.destination_lat is None:
        found = geocoder.geocode(request.destination)
        if not found:
            raise RoutingError('destination_not_found', '도착지 좌표를 확인해주세요.')
        lat, lng = found['lat'], found['lng']
    else:
        lat, lng = request.destination_lat, request.destination_lng
    vehicles = []
    for vehicle in request.vehicles:
        data = vehicle.model_dump()
        if data['start_lat'] is None:
            found = geocoder.geocode(vehicle.start_location)
            if not found:
                raise RoutingError('start_not_found', f'{vehicle.bus_id} 출발지를 찾지 못했습니다.')
            data.update(start_lat=found['lat'], start_lng=found['lng'])
        data.update(end_lat=lat, end_lng=lng, end_location=request.destination)
        vehicles.append(data)
    passengers = [p.model_dump() for p in request.passengers]
    options = request.options.model_dump()
    builder = MatrixBuilder()
    progress('matrix', 5, '도로 이동시간 계산')
    matrix = builder.build(passengers, vehicles, {'lat': lat, 'lng': lng},
        travel_time_factor=options['travel_time_factor'],
        progress=lambda done, total: progress('matrix', 5+int(30*done/total), f'도로 행렬 {done}/{total}'))
    warnings = []
    if matrix['matrix_source'] == 'haversine':
        if not options['allow_estimated']:
            raise RoutingError('road_data_unavailable', '도로 이동시간을 얻지 못했습니다. 도로 서버를 확인하거나 추정 계산을 명시적으로 허용해주세요.')
        warnings.append('직선거리 기반 추정 결과입니다. 실제 도로의 90분 이내 운행을 보장하지 않습니다.')
    progress('solver', 36, f"배차 탐색 중 (최대 {options['search_seconds']}초)")
    result = VRPSolver().solve(matrix['matrix'], passengers, vehicles, matrix['node_indices'],
        matrix['destination_idx'], matrix['vehicle_start_indices'], matrix['vehicle_end_indices'],
        options={k:v for k,v in options.items() if k not in ('travel_time_factor', 'allow_estimated')})
    destination = dict(address=request.destination, lat=lat, lng=lng,
                       arrival_time=request.arrival_time, service_date=request.service_date.isoformat())
    for route in result['routes']:
        route['stops'][-1].update(lat=lat, lng=lng, address=request.destination)
    progress('geometry', 70, '노선 지도 생성')
    builder.refine_with_road_api(result['routes'], matrix,
        progress=lambda done,total: progress('geometry', 70+int(25*done/total), f'지도 구간 {done}/{total}'))
    if any('estimated' in r['polyline_sources'] for r in result['routes']):
        warnings.append('일부 지도 구간은 직선으로 표시됩니다. 시간 계산 자료와 지도 표시 자료는 별개입니다.')
    progress('schedule', 96, '시간표 및 결과 검증')
    scheduled = TimeScheduler().calculate_times(result['routes'], request.arrival_time,
        matrix['matrix'], matrix['node_indices'], passengers, vehicles, matrix['destination_idx'],
        boarding_sec=options['boarding_sec'], service_date=request.service_date.isoformat())
    total = sum(r['total_passengers'] for r in scheduled)
    return dict(success=True, routes=scheduled, destination=destination,
        matrix_source=matrix['matrix_source'], warnings=warnings,
        optimization={**result['optimization'], 'options': options},
        unused_bus_ids=result['unused_bus_ids'],
        summary=dict(total_passengers=total, input_passengers=sum(p['passenger_count'] for p in passengers),
            total_buses=len(scheduled), available_buses=len(vehicles), unassigned_passengers=0,
            total_duration_min=round(sum(r['total_duration_sec'] for r in scheduled)/60,1),
            max_ride_min=max(r['max_ride_min'] for r in scheduled),
            average_ride_min=round(sum(r['passenger_time_sec'] for r in scheduled)/total/60,1)))


@router.post('/generate-route')
def generate_route(request: RouteRequest):
    # Compatibility endpoint uses the same single-job admission gate.
    from api.jobs import run_synchronous
    return run_synchronous(request)


@router.get('/debug-key')
def debug_key():
    return {'kakao_key_set': bool(os.environ.get('KAKAO_API_KEY')),
            'tmap_key_set': bool(os.environ.get('TMAP_API_KEY'))}


@router.get('/osrm-status')
def osrm_status():
    return check_osrm_health()


@router.delete('/cache')
def clear_cache():
    from api.jobs import work_lock
    if not work_lock.acquire(blocking=False):
        raise HTTPException(409, '계산이 끝난 뒤 캐시를 초기화해주세요.')
    try:
        for filename in ('geocode_cache.json', 'distance_cache.json', 'osrm_matrix_cache.json', 'osrm_route_cache.json'):
            DistanceCache(filename).clear()
    finally:
        work_lock.release()
    return {'message': '주소·도로 캐시를 초기화했습니다.'}
