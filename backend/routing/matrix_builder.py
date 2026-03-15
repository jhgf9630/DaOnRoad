"""
Distance Matrix 빌더
Step1: Haversine으로 초기 매트릭스 생성
Step2: VRP 실행 후 선택된 경로만 도로 API로 정교화
"""
from typing import List, Dict, Any
from routing.haversine import build_haversine_matrix
from routing.distance_engine import DistanceEngine


class MatrixBuilder:
    def __init__(self):
        self.engine = DistanceEngine()

    def build(self, passengers: List[Dict], vehicles: List[Dict],
              destination: Dict) -> Dict[str, Any]:
        """
        노드 구성:
          [0 .. N-1]  : 승객 픽업 위치
          [N]         : 행사장 (destination)
          [N+1 .. N+V]: 차량 출발지 (unique depot per vehicle)
          [N+V+1 ..]  : 차량 도착지 (one_way일 경우)
        """
        # 노드 목록 구성
        nodes = []
        node_indices = {"passengers": [], "destination": -1,
                        "vehicle_starts": [], "vehicle_ends": []}

        # 승객 노드
        for i, p in enumerate(passengers):
            nodes.append({"lat": p['lat'], "lng": p['lng'], "label": p['name']})
            node_indices["passengers"].append(i)

        # 행사장 노드
        dest_idx = len(nodes)
        nodes.append({"lat": destination['lat'], "lng": destination['lng'], "label": "행사장"})
        node_indices["destination"] = dest_idx

        # 차량 출발지 노드 (중복 허용 - 같은 위치라도 별도 노드)
        vehicle_start_indices = []
        for v in vehicles:
            idx = len(nodes)
            nodes.append({
                "lat": v.get('start_lat', destination['lat']),
                "lng": v.get('start_lng', destination['lng']),
                "label": f"{v['bus_id']}_start"
            })
            vehicle_start_indices.append(idx)
        node_indices["vehicle_starts"] = vehicle_start_indices

        # 차량 도착지 노드
        vehicle_end_indices = []
        for v in vehicles:
            end_lat = v.get('end_lat') or v.get('start_lat', destination['lat'])
            end_lng = v.get('end_lng') or v.get('start_lng', destination['lng'])
            idx = len(nodes)
            nodes.append({
                "lat": end_lat,
                "lng": end_lng,
                "label": f"{v['bus_id']}_end"
            })
            vehicle_end_indices.append(idx)
        node_indices["vehicle_ends"] = vehicle_end_indices

        # Haversine 매트릭스 생성
        matrix = build_haversine_matrix(nodes)

        return {
            "matrix": matrix,
            "nodes": nodes,
            "node_indices": node_indices,
            "destination_idx": dest_idx,
            "vehicle_start_indices": vehicle_start_indices,
            "vehicle_end_indices": vehicle_end_indices
        }

    def refine_with_road_api(self, routes: List[Dict], matrix_result: Dict):
        """
        VRP 솔버가 선택한 경로에 대해서만 실제 도로 API 호출로 정교화
        """
        nodes = matrix_result['nodes']
        matrix = matrix_result['matrix']

        for route in routes:
            stops = route.get('stops', [])
            for i in range(len(stops) - 1):
                from_node = stops[i]
                to_node = stops[i + 1]
                from_idx = from_node.get('node_idx', -1)
                to_idx = to_node.get('node_idx', -1)
                if from_idx < 0 or to_idx < 0:
                    continue
                from_loc = nodes[from_idx]
                to_loc = nodes[to_idx]

                # 도로 API로 실제 이동시간 조회
                road_time = self.engine.get_road_duration(
                    from_loc['lat'], from_loc['lng'],
                    to_loc['lat'], to_loc['lng']
                )
                # 매트릭스 업데이트 (해당 경로만)
                matrix[from_idx][to_idx] = road_time
                from_node['travel_time_sec'] = road_time
