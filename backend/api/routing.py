"""
DaOnRoad - 노선 생성 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from routing.matrix_builder import MatrixBuilder
from solver.vrp_solver import VRPSolver
from scheduler.time_scheduler import TimeScheduler
from routing.geocoder import Geocoder

router   = APIRouter()
geocoder = Geocoder()


class Passenger(BaseModel):
    name: str
    address: str
    passenger_count: int
    lat: float
    lng: float


class VehicleConfig(BaseModel):
    bus_id: str
    capacity: int
    start_location: str
    end_location: Optional[str] = None
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    end_lat:   Optional[float] = None
    end_lng:   Optional[float] = None


class RouteRequest(BaseModel):
    passengers:      List[Passenger]
    vehicles:        List[VehicleConfig]
    arrival_time:    str            # "HH:MM"
    destination:     str            # 도착지 주소
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None


@router.post("/generate-route")
async def generate_route(request: RouteRequest):
    try:
        # ── 1. 도착지 좌표 ───────────────────────────────
        if not request.destination_lat or not request.destination_lng:
            coord = geocoder.geocode(request.destination)
            if not coord:
                raise HTTPException(400, f"도착지 주소 좌표 변환 실패: {request.destination}")
            dest_lat, dest_lng = coord['lat'], coord['lng']
        else:
            dest_lat, dest_lng = request.destination_lat, request.destination_lng

        # ── 2. 차량 출발지 좌표 ──────────────────────────
        vehicles_data = []
        for v in request.vehicles:
            vd = v.dict()
            if not vd.get('start_lat') or not vd.get('start_lng'):
                coord = geocoder.geocode(v.start_location)
                if coord:
                    vd['start_lat'] = coord['lat']
                    vd['start_lng'] = coord['lng']
                else:
                    # fallback: 도착지 좌표 사용
                    vd['start_lat'] = dest_lat
                    vd['start_lng'] = dest_lng
            # end = destination (solver에서 처리하지만 명시)
            vd['end_lat']      = dest_lat
            vd['end_lng']      = dest_lng
            vd['end_location'] = request.destination
            vehicles_data.append(vd)

        # ── 3. Distance Matrix ───────────────────────────
        passengers_data = [p.dict() for p in request.passengers]
        matrix_builder  = MatrixBuilder()
        matrix_result   = matrix_builder.build(
            passengers=passengers_data,
            vehicles=vehicles_data,
            destination={"lat": dest_lat, "lng": dest_lng, "address": request.destination}
        )

        print(f"[routing] 노드수={len(matrix_result['matrix'])}, "
              f"승객={len(passengers_data)}, 차량={len(vehicles_data)}, "
              f"dest_idx={matrix_result['destination_idx']}")

        # ── 4. VRP Solver ────────────────────────────────
        solver   = VRPSolver()
        solution = solver.solve(
            distance_matrix=matrix_result['matrix'],
            passengers=passengers_data,
            vehicles=vehicles_data,
            node_indices=matrix_result['node_indices'],
            destination_idx=matrix_result['destination_idx'],
            vehicle_start_indices=matrix_result['vehicle_start_indices'],
            vehicle_end_indices=matrix_result['vehicle_end_indices']
        )

        if not solution['success'] or not solution['routes']:
            raise HTTPException(400,
                "노선 최적화 실패. 차량 총 정원이 총 승객 수 이상인지 확인하세요.")

        print(f"[routing] 생성된 노선 수: {len(solution['routes'])}")

        # ── 5. destination stop에 실제 좌표·주소 주입 ────
        for route in solution['routes']:
            for stop in route['stops']:
                if stop['type'] == 'destination':
                    stop['lat']     = dest_lat
                    stop['lng']     = dest_lng
                    stop['address'] = request.destination

        # ── 6. 도로 시간 정교화 (캐시 우선) ─────────────
        matrix_builder.refine_with_road_api(solution['routes'], matrix_result)

        # ── 7. 탑승시간 역산 ─────────────────────────────
        scheduler = TimeScheduler()
        scheduled = scheduler.calculate_times(
            routes=solution['routes'],
            arrival_time=request.arrival_time,
            distance_matrix=matrix_result['matrix'],
            node_indices=matrix_result['node_indices'],
            passengers_data=passengers_data,
            vehicles_data=vehicles_data,
            destination_idx=matrix_result['destination_idx']
        )

        print(f"[routing] 스케줄된 노선 수: {len(scheduled)}")

        if not scheduled:
            raise HTTPException(500, "시간 계산 결과가 비어있습니다. 서버 로그를 확인하세요.")

        return {
            "success": True,
            "routes":  scheduled,
            "destination": {
                "address":      request.destination,
                "lat":          dest_lat,
                "lng":          dest_lng,
                "arrival_time": request.arrival_time
            },
            "summary": {
                "total_passengers": sum(p['passenger_count'] for p in passengers_data),
                "total_buses":      len(scheduled),
                "total_duration_min": sum(r.get('total_duration_min', 0) for r in scheduled)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[routing ERROR]\n{tb}")
        raise HTTPException(500, f"노선 생성 오류: {str(e)}")


@router.post("/geocode")
async def geocode_address(body: Dict[str, str]):
    address = body.get("address", "").strip()
    if not address:
        raise HTTPException(400, "address 필드가 필요합니다.")
    coord = geocoder.geocode(address)
    if not coord:
        raise HTTPException(404, f"주소 변환 실패: {address}")
    return coord
