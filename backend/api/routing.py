"""
DaOnRoad - 노선 생성 + 주소 검색 API
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
    end_location:   Optional[str]   = None
    start_lat:      Optional[float] = None
    start_lng:      Optional[float] = None
    end_lat:        Optional[float] = None
    end_lng:        Optional[float] = None


class RouteRequest(BaseModel):
    passengers:      List[Passenger]
    vehicles:        List[VehicleConfig]
    arrival_time:    str
    destination:     str
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None


# ── 주소 검색 (자동완성 후보) ────────────────────────────────────
@router.post("/search-address")
async def search_address(body: Dict[str, Any]):
    """
    query 문자열로 주소/장소 후보 목록 반환
    응답: [{lat, lng, address, name, type, category?}, ...]
    """
    import os
    query = body.get("query", "").strip()
    limit = int(body.get("limit", 6))
    if not query:
        raise HTTPException(400, "query 필드가 필요합니다.")

    kakao_key = os.environ.get("KAKAO_API_KEY", "").strip()
    tmap_key  = os.environ.get("TMAP_API_KEY",  "").strip()

    print(f"[search-address] query='{query}' kakao={'있음' if kakao_key else '없음'}")

    if not kakao_key and not tmap_key:
        raise HTTPException(503,
            "API 키가 설정되지 않았습니다. backend/.env에 KAKAO_API_KEY를 추가하세요.")

    results = geocoder.search(query, limit=limit)
    print(f"[search-address] 결과 {len(results)}건")
    return {"results": results, "count": len(results)}


# ── 단일 좌표 변환 (하위 호환) ────────────────────────────────────
@router.post("/geocode")
async def geocode_address(body: Dict[str, str]):
    address = body.get("address", "").strip()
    if not address:
        raise HTTPException(400, "address 필드가 필요합니다.")
    results = geocoder.search(address, limit=1)
    if not results:
        raise HTTPException(404, f"주소 변환 실패: {address}\nKAKAO_API_KEY 또는 TMAP_API_KEY를 설정하세요.")
    return results[0]


# ── 노선 생성 ────────────────────────────────────────────────────
@router.post("/generate-route")
async def generate_route(request: RouteRequest):
    try:
        # 1. 도착지 좌표
        if not request.destination_lat or not request.destination_lng:
            results = geocoder.search(request.destination, limit=1)
            if not results:
                raise HTTPException(400,
                    f"도착지 주소 좌표 변환 실패: {request.destination}\n"
                    "KAKAO_API_KEY 또는 TMAP_API_KEY를 설정하세요.")
            dest_lat, dest_lng = results[0]['lat'], results[0]['lng']
        else:
            dest_lat, dest_lng = request.destination_lat, request.destination_lng

        # 2. 차량 출발지 좌표
        vehicles_data = []
        for v in request.vehicles:
            vd = v.dict()
            if not vd.get('start_lat') or not vd.get('start_lng'):
                results = geocoder.search(v.start_location, limit=1)
                if results:
                    vd['start_lat'] = results[0]['lat']
                    vd['start_lng'] = results[0]['lng']
                else:
                    # API 키 없으면 도착지 좌표로 대체 (경고)
                    print(f"[routing] 차량 {v.bus_id} 출발지 좌표 없음 → 도착지로 대체")
                    vd['start_lat'] = dest_lat
                    vd['start_lng'] = dest_lng
            vd['end_lat']      = dest_lat
            vd['end_lng']      = dest_lng
            vd['end_location'] = request.destination
            vehicles_data.append(vd)

        # 3. Distance Matrix
        passengers_data = [p.dict() for p in request.passengers]
        matrix_builder  = MatrixBuilder()
        matrix_result   = matrix_builder.build(
            passengers=passengers_data,
            vehicles=vehicles_data,
            destination={"lat": dest_lat, "lng": dest_lng, "address": request.destination}
        )

        print(f"[routing] 노드={len(matrix_result['matrix'])}, "
              f"승객={len(passengers_data)}, 차량={len(vehicles_data)}")

        # 4. VRP Solver
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
            raise HTTPException(400, "노선 최적화 실패. 차량 정원과 승객 수를 확인하세요.")

        print(f"[routing] 생성 노선: {len(solution['routes'])}")

        # 5. destination 좌표·주소 주입
        for route in solution['routes']:
            for stop in route['stops']:
                if stop['type'] == 'destination':
                    stop['lat']     = dest_lat
                    stop['lng']     = dest_lng
                    stop['address'] = request.destination

        # 6. 도로 시간 정교화
        matrix_builder.refine_with_road_api(solution['routes'], matrix_result)

        # 7. 시간 역산
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

        if not scheduled:
            raise HTTPException(500, "시간 계산 결과가 비어있습니다.")

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
                "total_passengers":   sum(p['passenger_count'] for p in passengers_data),
                "total_buses":        len(scheduled),
                "total_duration_min": sum(r.get('total_duration_min', 0) for r in scheduled)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[routing ERROR]\n{traceback.format_exc()}")
        raise HTTPException(500, f"노선 생성 오류: {str(e)}")


# ── 진단용 엔드포인트 ─────────────────────────────────────────────
@router.get("/debug-key")
async def debug_key():
    """API 키 설정 상태 및 Kakao 연결 테스트"""
    import os, requests as req
    kakao = os.environ.get("KAKAO_API_KEY", "").strip()
    tmap  = os.environ.get("TMAP_API_KEY",  "").strip()

    result = {
        "kakao_key_set": bool(kakao),
        "kakao_key_prefix": kakao[:8] + "..." if kakao else "",
        "tmap_key_set": bool(tmap),
    }

    # Kakao API 실제 호출 테스트
    if kakao:
        try:
            r = req.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {kakao}"},
                params={"query": "서울역", "size": 1},
                timeout=5
            )
            data = r.json()
            result["kakao_test_status"] = r.status_code
            result["kakao_test_ok"] = r.status_code == 200 and "documents" in data
            result["kakao_test_error"] = data.get("errorType") or data.get("message", "")
            result["kakao_result_count"] = len(data.get("documents", []))
        except Exception as e:
            result["kakao_test_ok"] = False
            result["kakao_test_error"] = str(e)

    return result


@router.delete("/cache")
async def clear_cache():
    """지오코딩 캐시 초기화"""
    geocoder.cache.clear()
    return {"message": "캐시가 초기화되었습니다."}
