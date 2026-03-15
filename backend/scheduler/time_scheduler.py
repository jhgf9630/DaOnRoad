"""
DaOnRoad - 시간 역산 모듈
도착지 도착시간 기준으로 각 탑승지 탑승시간 계산
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any

BOARDING_TIME_SEC = 120  # 탑승 대기/승하차 시간 (2분)


class TimeScheduler:
    def calculate_times(self,
                        routes: List[Dict],
                        arrival_time: str,
                        distance_matrix: List[List[int]],
                        node_indices: Dict,
                        passengers_data: List[Dict],
                        vehicles_data: List[Dict],
                        destination_idx: int) -> List[Dict]:
        arrival_dt = datetime.strptime(arrival_time, "%H:%M")
        scheduled = []

        for route in routes:
            stops = route.get('stops', [])
            if not stops:
                continue

            # destination 정류장 위치
            dest_stop_idx = next(
                (i for i, s in enumerate(stops) if s['type'] == 'destination'), -1
            )
            if dest_stop_idx < 0:
                continue

            current_time = arrival_dt

            # 역산: destination 바로 앞 정류장부터 역방향으로
            for i in range(dest_stop_idx - 1, -1, -1):
                stop = stops[i]
                next_stop = stops[i + 1]

                travel_sec = self._get_travel_time(stop, next_stop, distance_matrix)
                board_sec = BOARDING_TIME_SEC if stop['type'] == 'pickup' else 0
                current_time -= timedelta(seconds=travel_sec + board_sec)
                # ★ pickup_time_dt는 저장하지 않음 (JSON 직렬화 불가)
                stops[i]['pickup_time'] = current_time.strftime("%H:%M")

            # destination 시간
            stops[dest_stop_idx]['pickup_time'] = arrival_time

            # 출발시간 = 첫 stop의 시간
            departure_time = stops[0].get('pickup_time', arrival_time)

            total_duration_min = self._calc_route_duration(stops, distance_matrix)

            scheduled.append({
                **route,
                "stops": stops,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "total_duration_min": total_duration_min
            })

        return scheduled

    def _get_travel_time(self, from_stop: Dict, to_stop: Dict,
                         distance_matrix: List[List[int]]) -> int:
        from_idx = from_stop.get('node_idx', -1)
        to_idx   = to_stop.get('node_idx', -1)

        if from_stop.get('travel_time_sec', 0) > 0:
            return from_stop['travel_time_sec']

        if from_idx >= 0 and to_idx >= 0 and distance_matrix:
            try:
                return distance_matrix[from_idx][to_idx]
            except IndexError:
                pass

        return 600

    def _calc_route_duration(self, stops: List[Dict],
                              distance_matrix: List[List[int]]) -> int:
        total_sec = 0
        for i in range(len(stops) - 1):
            total_sec += self._get_travel_time(stops[i], stops[i + 1], distance_matrix)
            if stops[i]['type'] == 'pickup':
                total_sec += BOARDING_TIME_SEC
        return round(total_sec / 60)
