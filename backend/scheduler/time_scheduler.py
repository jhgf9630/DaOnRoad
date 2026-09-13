"""Date-aware backward scheduling using exact solver travel and service times."""
from datetime import date, datetime, timedelta

BOARDING_SEC = 120


class TimeScheduler:
    def calculate_times(self, routes, arrival_time, distance_matrix, node_indices,
                        passengers_data, vehicles_data, destination_idx,
                        boarding_sec=BOARDING_SEC, service_date=None):
        day = date.fromisoformat(service_date) if service_date else date.today()
        arrival = datetime.combine(day, datetime.strptime(arrival_time, '%H:%M').time())
        scheduled = []
        for route in routes:
            stops = route['stops']
            if not stops or stops[0]['type'] != 'start' or stops[-1]['type'] != 'destination':
                raise ValueError('출발지와 도착지가 있는 완전한 노선만 시간표를 생성할 수 있습니다.')
            current = arrival
            for i in range(len(stops) - 1, -1, -1):
                stop = stops[i]
                if i < len(stops) - 1:
                    travel = distance_matrix[stop['node_idx']][stops[i + 1]['node_idx']]
                    stop['travel_time_sec'] = travel
                    current -= timedelta(seconds=travel + (boarding_sec if stop['type'] == 'pickup' else 0))
                stop['pickup_time'] = current.strftime('%H:%M')
                stop['pickup_datetime'] = current.isoformat()
                stop['day_offset'] = (current.date() - day).days
                if stop['type'] == 'pickup':
                    stop['ride_time_sec'] = int((arrival - current).total_seconds())
                    stop['ride_time_min'] = round(stop['ride_time_sec'] / 60, 1)
            first = next(s for s in stops if s['type'] == 'pickup')
            duration = int((arrival - current).total_seconds())
            scheduled.append({**route, 'stops': stops,
                'departure_time': stops[0]['pickup_time'],
                'departure_datetime': stops[0]['pickup_datetime'],
                'departure_day_offset': stops[0]['day_offset'],
                'first_pickup_time': first['pickup_time'],
                'arrival_time': arrival_time, 'arrival_datetime': arrival.isoformat(),
                'total_duration_sec': duration, 'total_duration_min': round(duration / 60, 1)})
        return scheduled
