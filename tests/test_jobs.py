import threading
import time
from fastapi.testclient import TestClient
from main import app
import api.jobs as jobs
import api.routing as routing

client=TestClient(app,headers={'X-DaOnRoad-Client':'desktop-v1'})


def payload():
    return dict(passengers=[dict(name='a',address='a',passenger_count=1,lat=37.5,lng=127.)],
        vehicles=[dict(bus_id='bus',capacity=21,start_location='start',start_lat=37.5,start_lng=127.)],
        destination='school',destination_lat=37.5,destination_lng=127.,arrival_time='10:00',
        service_date='2026-09-13',options={'search_seconds':1,'allow_estimated':True})


def wait_job(job_id):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        status=client.get('/api/route-jobs/'+job_id).json()
        if status['status'] in ('completed','failed','cancelled'):
            return status
        time.sleep(.02)
    raise AssertionError('job timeout')


def test_route_job_roundtrip_and_export():
    response=client.post('/api/route-jobs',json=payload())
    assert response.status_code==202
    result=wait_job(response.json()['job_id'])
    assert result['status']=='completed'
    data=result['result']
    assert data['summary']['total_passengers']==1
    assert data['routes'][0]['total_duration_sec']==120
    assert data['warnings']
    assert client.post('/api/export',json=data).status_code==200


def test_busy_health_and_cancellation(monkeypatch):
    started,released=threading.Event(),threading.Event()
    def work(request,progress):
        progress('test',10,'test');started.set();released.wait(3)
        progress('test',99,'test')
        return {}
    monkeypatch.setattr(routing,'calculate_route',work)
    job=client.post('/api/route-jobs',json=payload()).json()['job_id']
    assert started.wait(2)
    try:
        assert client.get('/health').status_code==200
        assert client.post('/api/route-jobs',json=payload()).status_code==409
        assert client.post('/api/generate-route',json=payload()).status_code==409
        assert client.delete('/api/route-jobs/'+job).status_code==202
    finally:
        released.set()
    assert wait_job(job)['status']=='cancelled'


def test_estimated_plan_requires_explicit_choice():
    request=payload();request['options']['allow_estimated']=False
    response=client.post('/api/generate-route',json=request)
    assert response.status_code==422
    assert response.json()['detail']['code']=='road_data_unavailable'


def test_duplicate_bus_and_bad_time_are_validation_errors():
    request=payload();request['vehicles']*=2
    assert client.post('/api/route-jobs',json=request).status_code==422
    request=payload();request['arrival_time']='25:00'
    assert client.post('/api/route-jobs',json=request).status_code==422
