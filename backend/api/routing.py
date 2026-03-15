"""
노선 생성 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from routing.matrix_builder import MatrixBuilder
from solver.vrp_solver import VRPSolver
from scheduler.time_scheduler import TimeScheduler
from routing.geocoder import Geocoder

router = APIRouter()
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
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None


class RouteRequest(BaseModel):
    passengers: List[Passenger]
    vehicles: List[VehicleConfig]
    arrival_time: str          # "HH:MM"
    destination: str           # 행사장 주소
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    route_type: str = "round"  # "round" | "one_way"


@router.post("/generate-route")
async def generate_route(request: RouteRequest):
    """
    VRP 알고리즘으로 최적 버스 노선 생성
    """
    try:
        # 1. 행사장 좌표 확인
        if not request.destination_lat or not request.destination_lng:
            coord = geocoder.geocode(request.destination)
            if not coord:
                raise HTTPException(status_code=400, detail=f"행사장 주소 좌표 변환 실패: {request.destination}")
            dest_lat, dest_lng = coord['lat'], coord['lng']
        else:
            dest_lat, dest_lng = request.destination_lat, request.destination_lng

        # 2. 차량 출발지/도착지 좌표 확인
        vehicles_data = []
        for v in request.vehicles:
            vd = v.dict()
            if not v.start_lat or not v.start_lng:
                coord = geocoder.geocode(v.start_location)
                if coord:
                    vd['start_lat'] = coord['lat']
                    vd['start_lng'] = coord['lng']
            if request.route_type == "round":
                vd['end_lat'] = vd['start_lat']
                vd['end_lng'] = vd['start_lng']
                vd['end_location'] = vd['start_location']
            elif v.end_location and (not v.end_lat or not v.end_lng):
                coord = geocoder.geocode(v.end_location)
                if coord:
                    vd['end_lat'] = coord['lat']
                    vd['end_lng'] = coord['lng']
            vehicles_data.append(vd)

        # 3. Distance Matrix 생성
        passengers_data = [p.dict() for p in request.passengers]
        matrix_builder = MatrixBuilder()
        matrix_result = matrix_builder.build(
            passengers=passengers_data,
            vehicles=vehicles_data,
            destination={"lat": dest_lat, "lng": dest_lng, "address": request.destination}
        )

        # 4. VRP Solver 실행
        solver = VRPSolver()
        solution = solver.solve(
            distance_matrix=matrix_result['matrix'],
            passengers=passengers_data,
            vehicles=vehicles_data,
            node_indices=matrix_result['node_indices'],
            destination_idx=matrix_result['destination_idx'],
            vehicle_start_indices=matrix_result['vehicle_start_indices'],
            vehicle_end_indices=matrix_result['vehicle_end_indices']
        )

        if not solution['success']:
            raise HTTPException(status_code=400, detail="노선 최적화에 실패했습니다. 차량 수 또는 용량을 확인해주세요.")

        # 5. 실제 도로 시간으로 업데이트 (캐시 활용)
        matrix_builder.refine_with_road_api(solution['routes'], matrix_result)

        # 6. 시간 역산
        scheduler = TimeScheduler()
        scheduled_routes = scheduler.calculate_times(
            routes=solution['routes'],
            arrival_time=request.arrival_time,
            distance_matrix=matrix_result['matrix'],
            node_indices=matrix_result['node_indices'],
            passengers_data=passengers_data,
            vehicles_data=vehicles_data,
            destination_idx=matrix_result['destination_idx']
        )

        return {
            "success": True,
            "routes": scheduled_routes,
            "destination": {
                "address": request.destination,
                "lat": dest_lat,
                "lng": dest_lng,
                "arrival_time": request.arrival_time
            },
            "summary": {
                "total_passengers": sum(p['passenger_count'] for p in passengers_data),
                "total_buses": len(scheduled_routes),
                "total_duration_min": sum(r.get('total_duration_min', 0) for r in scheduled_routes)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"노선 생성 오류: {str(e)}\n{traceback.format_exc()}")


@router.post("/geocode")
async def geocode_address(body: Dict[str, str]):
    """단일 주소 좌표 변환"""
    address = body.get("address")
    if not address:
        raise HTTPException(status_code=400, detail="address 필드가 필요합니다.")
    coord = geocoder.geocode(address)
    if not coord:
        raise HTTPException(status_code=404, detail=f"주소 변환 실패: {address}")
    return coord
