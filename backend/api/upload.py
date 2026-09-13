"""Excel upload validation. No failed row is silently accepted for planning."""
import io
import math
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from routing.geocoder import Geocoder

router = APIRouter()
geocoder = Geocoder()
MAX_BYTES = 10 * 1024 * 1024


@router.post('/upload')
def upload_excel(file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith(('.xlsx','.xls')):
        raise HTTPException(400, 'Excel 파일(.xlsx, .xls)만 업로드 가능합니다.')
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'Excel 파일은 10MB 이하로 업로드해주세요.')
    try:
        df = pd.read_excel(io.BytesIO(content), nrows=1001)
    except Exception:
        raise HTTPException(400, 'Excel 파일을 읽을 수 없습니다. 파일 형식을 확인해주세요.')
    if len(df) > 1000:
        raise HTTPException(400, '한 번에 최대 1,000행까지 처리할 수 있습니다.')
    df.columns = [str(c).strip() for c in df.columns]
    df.rename(columns={'이름':'name','성명':'name','주소':'address','탑승지':'address',
                       '인원':'passenger_count','탑승인원':'passenger_count','명':'passenger_count'}, inplace=True)
    if df.columns.duplicated().any():
        raise HTTPException(400, '동일한 의미의 컬럼이 중복됩니다.')
    required = ['name','address','passenger_count']
    if any(c not in df.columns for c in required):
        raise HTTPException(400, '이름(name), 주소(address), 인원(passenger_count) 컬럼이 필요합니다.')
    if df.empty:
        raise HTTPException(400, '학생 데이터가 없습니다.')
    passengers, errors = [], []
    for i,row in df.iterrows():
        try:
            if pd.isna(row['name']) or pd.isna(row['address']):
                raise ValueError()
            name,address = str(row['name']).strip(),str(row['address']).strip()
            count = float(row['passenger_count'])
            if not name or not address or len(name)>200 or len(address)>500 or not math.isfinite(count) or not count.is_integer() or not 1<=count<=1000:
                raise ValueError()
            passengers.append(dict(name=name,address=address,passenger_count=int(count),row_number=int(i)+2))
        except (ValueError, TypeError):
            errors.append(int(i)+2)
    if errors:
        raise HTTPException(422, {'message':'이름·주소와 양의 정수 인원을 확인해주세요. 행을 자동 삭제하지 않습니다.', 'rows':errors})
    unique = list(dict.fromkeys(p['address'] for p in passengers))
    with ThreadPoolExecutor(max_workers=4) as pool:
        coords = dict(zip(unique, pool.map(geocoder.geocode, unique)))
    for p in passengers:
        coord=coords[p['address']]
        p.update(lat=coord['lat'] if coord else None,lng=coord['lng'] if coord else None,geocoded=coord is not None)
    failed=[p for p in passengers if not p['geocoded']]
    return dict(total=len(passengers),success=len(passengers)-len(failed),failed=len(failed),
                total_passengers=sum(p['passenger_count'] for p in passengers),
                passengers=passengers,failed_addresses=[p['address'] for p in failed])
