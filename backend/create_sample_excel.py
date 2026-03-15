"""
테스트용 샘플 Excel 파일 생성
실행: python create_sample_excel.py
"""
import pandas as pd

sample_data = [
    {"name": "홍길동", "address": "서울 강남구 역삼동", "passenger_count": 1},
    {"name": "김철수", "address": "인천 연수구 송도동", "passenger_count": 2},
    {"name": "박영희", "address": "경기 부천시 중동", "passenger_count": 1},
    {"name": "이민준", "address": "서울 서초구 반포동", "passenger_count": 3},
    {"name": "최수진", "address": "경기 수원시 팔달구", "passenger_count": 1},
    {"name": "정태양", "address": "인천 부평구", "passenger_count": 2},
    {"name": "강나래", "address": "서울 마포구 상암동", "passenger_count": 1},
    {"name": "윤도현", "address": "경기 성남시 분당구", "passenger_count": 2},
    {"name": "임지현", "address": "서울 노원구 상계동", "passenger_count": 1},
    {"name": "한기준", "address": "경기 고양시 일산동구", "passenger_count": 3},
    {"name": "조민서", "address": "서울 강서구 화곡동", "passenger_count": 1},
    {"name": "신예린", "address": "경기 안양시 동안구", "passenger_count": 2},
    {"name": "오병훈", "address": "서울 송파구 잠실동", "passenger_count": 1},
    {"name": "배수현", "address": "인천 남동구 구월동", "passenger_count": 2},
    {"name": "문재원", "address": "경기 용인시 수지구", "passenger_count": 1},
]

df = pd.DataFrame(sample_data)
df.to_excel("sample_passengers.xlsx", index=False)
print(f"✅ sample_passengers.xlsx 생성 완료 ({len(df)}명)")
print(f"   총 탑승인원: {df['passenger_count'].sum()}명")
