"""
DaOnRoad - 시간 역산 모듈
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any

BOARDING_SEC = 120  # 탑승 대기 2분


class TimeScheduler:
    def calculate_times(self, routes, arrival_time,
                        distance_matrix, node_indices,
                        passengers_data, vehicles_data, destination_idx):

        arrival_dt = datetime.strptime(arrival_time, "%H:%M")
        scheduled  = []

        for route in routes:
            stops = route.get('stops', [])
            if not stops:
                print(f"[scheduler] {route.get('bus_id')} stops 비어있음 - 스킵")
                continue

            # destination 위치 탐색
            dest_idx = next(
                (i for i, s in enumerate(stops) if s['type'] == 'destination'), -1
            )

            # destination 이 없으면 마지막에 가상으로 추가
            if dest_idx < 0:
                print(f"[scheduler] {route.get('bus_id')} destination 없음 - 끝에 추가")
                stops.append({
                    "order": len(stops),
                    "node_idx": destination_idx,
                    "type": "destination",
                    "name": "도착지",
                    "address": "",
                    "lat": None, "lng": None,
                    "travel_time_sec": 0,
                    "pickup_time": ""
                })
                dest_idx = len(stops) - 1

            # 역산: destination부터 첫 번째 stop까지
            current_time = arrival_dt
            stops[dest_idx]['pickup_time'] = arrival_time

            for i in range(dest_idx - 1, -1, -1):
                stop      = stops[i]
                next_stop = stops[i + 1]
                travel    = self._travel(stop, next_stop, distance_matrix)
                board     = BOARDING_SEC if stop['type'] == 'pickup' else 0
                current_time -= timedelta(seconds=travel + board)
                stop['pickup_time'] = current_time.strftime("%H:%M")

            # start stop 시간 = departure
            departure = stops[0].get('pickup_time', arrival_time)
            if stops[0]['type'] == 'start':
                # start는 표시용이고 실제 첫 픽업 시간을 departure로
                first_pickup = next(
                    (s for s in stops if s['type'] == 'pickup'), None
                )
                departure = first_pickup['pickup_time'] if first_pickup else arrival_time

            duration = self._duration(stops, distance_matrix)

            scheduled.append({
                **route,
                "stops":            stops,
                "departure_time":   departure,
                "arrival_time":     arrival_time,
                "total_duration_min": duration
            })

        return scheduled

    def _travel(self, from_stop, to_stop, matrix):
        if from_stop.get('travel_time_sec', 0) > 0:
            return from_stop['travel_time_sec']
        fi = from_stop.get('node_idx', -1)
        ti = to_stop.get('node_idx', -1)
        if fi >= 0 and ti >= 0 and matrix:
            try:
                return matrix[fi][ti]
            except IndexError:
                pass
        return 600  # 기본 10분

    def _duration(self, stops, matrix):
        total = 0
        for i in range(len(stops) - 1):
            total += self._travel(stops[i], stops[i+1], matrix)
            if stops[i]['type'] == 'pickup':
                total += BOARDING_SEC
        return round(total / 60)
