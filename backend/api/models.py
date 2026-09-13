"""Validated API contracts for reproducible transport planning."""
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)


class Passenger(Model):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    passenger_count: int = Field(ge=1, le=1000, strict=True)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class VehicleConfig(Model):
    bus_id: str = Field(min_length=1, max_length=80)
    capacity: int = Field(ge=1, le=200, strict=True)
    start_location: str = Field(min_length=1, max_length=500)
    start_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    start_lng: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode='after')
    def coordinate_pair(self):
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError('출발지 위도·경도를 함께 입력해주세요.')
        return self


class OptimizationOptions(Model):
    max_ride_min: float = Field(default=90, ge=1, le=240)
    max_route_min: float = Field(default=240, ge=1, le=720)
    boarding_sec: int = Field(default=120, ge=0, le=600, strict=True)
    vehicle_fixed_cost_min: float = Field(default=30, ge=0, le=1440)
    passenger_time_weight: float = Field(default=.2, ge=0, le=10)
    use_all_vehicles: bool = False
    search_seconds: int = Field(default=60, ge=1, le=180, strict=True)
    travel_time_factor: float = Field(default=1.0, ge=1, le=3)
    allow_estimated: bool = False


class RouteRequest(Model):
    passengers: list[Passenger] = Field(min_length=1, max_length=1000)
    vehicles: list[VehicleConfig] = Field(min_length=1, max_length=100)
    arrival_time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    service_date: date = Field(default_factory=date.today)
    destination: str = Field(min_length=1, max_length=500)
    destination_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    options: OptimizationOptions = Field(default_factory=OptimizationOptions)

    @model_validator(mode='after')
    def validate_plan(self):
        if len({v.bus_id for v in self.vehicles}) != len(self.vehicles):
            raise ValueError('버스 ID가 중복됩니다.')
        if (self.destination_lat is None) != (self.destination_lng is None):
            raise ValueError('도착지 위도·경도를 함께 입력해주세요.')
        if sum(p.passenger_count for p in self.passengers) > sum(v.capacity for v in self.vehicles):
            raise ValueError('학생 수가 전체 차량 정원을 초과합니다.')
        if any(p.passenger_count > max(v.capacity for v in self.vehicles) for p in self.passengers):
            raise ValueError('한 행의 인원이 최대 차량 정원보다 큽니다. 그룹은 분할하지 않습니다.')
        return self


class SearchRequest(Model):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=6, ge=1, le=15)
