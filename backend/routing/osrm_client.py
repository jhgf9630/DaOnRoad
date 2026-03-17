"""
DaOnRoad - OSRM Client (osrm_service.py로 통합됨)
하위 호환성 유지용 shim
"""
from routing.osrm_service import (
    build_osrm_matrix,
    get_route_polyline,
    get_routes_polylines,
    check_osrm_health,
)

__all__ = ["build_osrm_matrix", "get_route_polyline",
           "get_routes_polylines", "check_osrm_health"]
