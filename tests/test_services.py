from concurrent.futures import ThreadPoolExecutor
import io
import json
import pandas as pd
from openpyxl import load_workbook
import pytest
from fastapi.testclient import TestClient
from main import app
from routing.distance_cache import DistanceCache
from routing import osrm_service as osrm

client=TestClient(app,headers={'X-DaOnRoad-Client':'desktop-v1'})


def test_matrix_tiling_both_axes_and_asymmetry(monkeypatch):
    monkeypatch.setenv('OSRM_TABLE_COORD_LIMIT','4')
    nodes=[dict(lat=i,lng=i) for i in range(7)]
    def table(local,sources=None,destinations=None):
        assert len(local)<=4
        return [[local[a]['lat']*100+local[b]['lat'] for b in destinations] for a in sources]
    monkeypatch.setattr(osrm,'_table_request',table)
    assert osrm._build_matrix_chunked(nodes)==[[a*100+b for b in range(7)] for a in range(7)]


def test_unreachable_is_not_straight_line(monkeypatch):
    monkeypatch.setenv('OSRM_BASE_URL','http://osrm:5000')
    monkeypatch.setattr(osrm,'_build_matrix_chunked',lambda *a:[[0,None],[0,0]])
    matrix,source=osrm.build_osrm_matrix([{'lat':37,'lng':127},{'lat':38,'lng':127}],False)
    assert source=='osrm'
    assert matrix[0][1]==osrm.UNREACHABLE
    assert matrix[1][0]==0


def test_hostname_recognition(monkeypatch):
    for url,expected in [('http://osrm:5000',True),('http://172.18.0.2:5000',True),('http://localhost.evil.example',False)]:
        monkeypatch.setenv('OSRM_BASE_URL',url)
        assert osrm._is_local()==expected


def test_cache_shared_atomic_clear():
    a,b=DistanceCache('test.json'),DistanceCache('test.json')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i:(a if i%2 else b).set(str(i),i),range(30)))
    assert all(a.get(str(i))==i for i in range(30))
    assert json.loads(open(a.cache_path,encoding='utf-8').read())['version']==2
    b.clear()
    assert a.get('0') is None


def test_cache_expiry():
    cache=DistanceCache('expiry.json');cache.set('a',1,ttl=-1)
    assert cache.get('a') is None


def test_untrusted_origin_and_missing_client_header():
    assert client.get('/api/debug-key',headers={'Origin':'https://evil.example'}).status_code==403
    assert TestClient(app).get('/api/debug-key').status_code==403
    assert client.get('/health').status_code==200
    assert 'kakao_key_prefix' not in client.get('/api/debug-key').json()


def upload(rows):
    buf=io.BytesIO();pd.DataFrame(rows).to_excel(buf,index=False)
    return client.post('/api/upload',files={'file':('sample.xlsx',buf.getvalue())})


@pytest.mark.parametrize('count',[0,-1,1.5,None])
def test_invalid_excel_counts_rejected(count):
    response=upload([dict(name='student',address='address',passenger_count=count)])
    assert response.status_code==422


def test_missing_address_not_silently_dropped():
    assert upload([dict(name='student',address=None,passenger_count=1)]).status_code==422


def test_geocode_failures_preserved(monkeypatch):
    import api.upload as module
    monkeypatch.setattr(module.geocoder,'geocode',lambda addr:None)
    data=upload([dict(name='student',address='unknown',passenger_count=2)]).json()
    assert data['failed']==1 and len(data['passengers'])==1 and data['total_passengers']==2


def test_export_neutralizes_formula():
    from export.excel_exporter import ExcelExporter
    data=ExcelExporter().export([dict(bus_id='=1+1',stops=[dict(type='pickup',name='=HYPERLINK("x")',address='address',passenger_count=1)])],{})
    workbook=load_workbook(io.BytesIO(data))
    assert workbook['Passenger']['A2'].data_type=='s'
    assert workbook['Passenger']['B2'].data_type=='s'
