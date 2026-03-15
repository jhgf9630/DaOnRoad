"""
Excel 파일 업로드 및 파싱 API
"""
import io
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import pandas as pd
from routing.geocoder import Geocoder

router = APIRouter()
geocoder = Geocoder()


@router.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    """
    Excel 파일 업로드 → 승객 데이터 파싱 → 좌표 변환
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Excel 파일(.xlsx, .xls)만 업로드 가능합니다.")

    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content))

        # 필수 컬럼 확인
        required_cols = ['name', 'address', 'passenger_count']
        # 한글 컬럼명 매핑
        col_map = {
            '이름': 'name', '성명': 'name',
            '주소': 'address', '탑승지': 'address',
            '인원': 'passenger_count', '탑승인원': 'passenger_count', '명': 'passenger_count'
        }
        df.rename(columns=col_map, inplace=True)

        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"필수 컬럼 누락: {missing}. 필요한 컬럼: name(이름), address(주소), passenger_count(인원)"
            )

        df = df.dropna(subset=['name', 'address'])
        df['passenger_count'] = df['passenger_count'].fillna(1).astype(int)

        passengers = []
        for _, row in df.iterrows():
            coord = geocoder.geocode(str(row['address']))
            passengers.append({
                "name": str(row['name']),
                "address": str(row['address']),
                "passenger_count": int(row['passenger_count']),
                "lat": coord['lat'] if coord else None,
                "lng": coord['lng'] if coord else None,
                "geocoded": coord is not None
            })

        failed = [p for p in passengers if not p['geocoded']]
        success = [p for p in passengers if p['geocoded']]

        return {
            "total": len(passengers),
            "success": len(success),
            "failed": len(failed),
            "passengers": passengers,
            "failed_addresses": [p['address'] for p in failed]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 처리 오류: {str(e)}")
