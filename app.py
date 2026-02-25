import streamlit as st
import pandas as pd
import requests
from geopy.geocoders import Nominatim
import numpy as np

# --- [설정] ---
st.set_page_config(page_title="GS25 매출비교 기반 발주", layout="centered")

# --- [함수: 위치 및 날씨 (기존과 동일)] ---
def get_location(store_name):
    try:
        geolocator = Nominatim(user_agent="gs25_manager_app_v3")
        loc = geolocator.geocode(f"{store_name}, South Korea")
        if loc: return loc.latitude, loc.longitude, loc.address
        return None, None, None
    except: return None, None, None

def get_forecast(lat, lon, days_later=1):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,precipitation_sum&timezone=auto"
        res = requests.get(url).json()
        idx = days_later
        t_max = res['daily']['temperature_2m_max'][idx]
        rain = res['daily']['precipitation_sum'][idx]
        return {"temp": t_max, "rain_mm": rain, "is_rainy": rain > 5.0}
    except:
        return {"temp": 25, "rain_mm": 0, "is_rainy": False}

# --- [메인 화면] ---
st.title("📊 GS25 매출비교 기반 스마트 발주")
st.markdown("매출비교(PDF/엑셀) 데이터를 업로드하면 **조회기간의 판매량**을 기준으로 발주를 제안합니다.")

# 1. 점포 및 날씨 설정
with st.expander("🛠️ 점포 환경 및 날씨 설정 (클릭)", expanded=False):
    store_name = st.text_input("점포명", "GS25 강남역점")
    target_day_str = st.selectbox("입고일", ["내일", "모레"])
    day_offset = 1 if target_day_str == "내일" else 2
    
    weather = {"temp": 25, "rain_mm": 0, "is_rainy": False}
    if store_name:
        lat, lon, addr = get_location(store_name)
        if lat:
            st.success(f"📍 {addr}")
            weather = get_forecast(lat, lon, day_offset)
            st.info(f"🌡️ {weather['temp']}°C | ☔ {weather['rain_mm']}mm ({'비옴' if weather['is_rainy'] else '맑음'})")

# 2. 데이터 기간 설정 (중요!)
st.write("---")
col_d1, col_d2 = st.columns(2)
with col_d1:
    data_days = st.number_input("업로드할 데이터의 조회 기간(일)", min_value=1, value=7, help="매출비교 리포트가 최근 7일치면 7, 30일치면 30을 입력하세요.")
with col_d2:
    target_stock_days = st.number_input("목표 재고 일수", min_value=1.0, value=2.5, step=0.5, help="하루에 1개 팔리면 2.5개를 재고로 둡니다.")

# 3. 파일 업로드
uploaded_file = st.file_uploader("매출비교 엑셀/CSV 파일 업로드", type=['csv', 'xlsx'])

if uploaded_file:
    # --- [데이터 로딩 및 전처리 로직] ---
    try:
        # 1. 파일 읽기 (2번째 줄이 헤더이므로 header=1)
        # CSV인지 엑셀인지 자동 판별은 어려우므로 try-except 사용하거나 pd.read_csv 시도
        if uploaded_file.name.endswith('.xlsx'):
            df_raw = pd.read_excel(uploaded_file, header=1)
        else:
            try:
                df_raw = pd.read_csv(uploaded_file, header=1)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, header=1, encoding='cp949')

        # 2. 핵심 컬럼 추출 (이름이 중복되므로 위치(Index)로 가져오는 게 가장 정확함)
        # 보통 구조: [0]상품명 ... [4]판매수량(조회기간) ... [10]재고수량(추정)
        # 안전을 위해 컬럼 이름에 '판매'와 '재고'가 포함된 컬럼을 찾습니다.
        
        # 컬럼명 공백 제거
        df_raw.columns = [str(c).replace(" ", "").replace("\n", "") for c in df_raw.columns]
        
        # 필요한 데이터만 뽑아서 새로운 데이터프레임 생성
        df = pd.DataFrame()
        
        # (1) 상품명: 첫 번째 컬럼
        df['상품명'] = df_raw.iloc[:, 0]
        
        # (2) 카테고리: 보통 '등급' 앞이나 뒤에 있음, 없으면 빈칸 처리
        if '카테고리' in df_raw.columns:
            df['카테고리'] = df_raw['카테고리']
        else:
            df['카테고리'] = '기타' # 카테고리 정보가 없으면 기타

        # (3) 판매수량: '판매수량'이라는 이름의 컬럼 중 '첫 번째' 것 (조회기간)
        sales_cols = [c for c in df_raw.columns if '판매수량' in c]
        if len(sales_cols) > 0:
            df['기간판매량'] = df_raw[sales_cols[0]] # 첫번째 판매수량 사용
        else:
            st.error("파일에서 '판매수량' 열을 찾을 수 없습니다.")
            st.stop()
            
        # (4) 재고수량: '재고'가 들어간 컬럼
        stock_cols = [c for c in df_raw.columns if '재고' in c]
        if len(stock_cols) > 0:
            df['현재재고'] = df_raw[stock_cols[0]]
        else:
            # 재고 컬럼이 없으면 10번째(Index 10) 시도 (업로드해주신 샘플 기준)
            if len(df_raw.columns) > 10:
                 df['현재재고'] = df_raw.iloc[:, 10]
            else:
                df['현재재고'] = 0

        # (5) 행사정보: '행사'가 들어간 컬럼
        event_cols = [c for c in df_raw.columns if '행사' in c]
        if len(event_cols) > 0:
            df['행사'] = df_raw[event_cols[0]]
        else:
             df['행사'] = ''

        # --- [데이터 클렌징 (숫자 변환)] ---
        def clean_number(x):
            try:
                if pd.isna(x) or str(x).strip() == '': return 0
                # 쉼표 제거 및 숫자 변환
                return float(str(x).replace(',', ''))
            except:
                return 0

        df['기간판매량'] = df['기간판매량'].apply(clean_number)
        df['현재재고'] = df['현재재고'].apply(clean_number)
        
        # 상품명이 없는 줄(합계 등) 제거
        df = df[df['상품명'].notna()]
        df = df[df['상품명'] != '']

        # --- [발주 계산 로직] ---
        def calculate_order(row):
            # 1. 일평균 판매량 계산
            daily_sales = row['기간판매량'] / data_days
            
            # 2. 목표 재고량 (일평균 * 목표일수)
            target = daily_sales * target_stock_days
            
            # 3. 가중치 적용 (날씨/행사)
            weight = 1.0
            
            name = str(row['상품명'])
            cat = str(row['카테고리'])
            
            # 날씨
            if weather['temp'] >= 28:
                if '얼음' in name or '아이스' in name or '음료' in cat: weight += 0.3
            if weather['is_rainy']:
                if '우산' in name: weight += 4.0
                if '면류' in cat or '국물' in name: weight += 0.2
            
            # 행사 (행사 정보가 있다면)
            if '1+1' in str(row['행사']): weight += 0.5
            elif '2+1' in str(row['행사']): weight += 0.3
            
            # 4. 최종 필요량 - 현재재고
            needed = (target * weight) - row['현재재고']
            return max(0, int(needed))

        df['추천발주'] = df.apply(calculate_order, axis=1)

        # --- [결과 화면] ---
        st.subheader("📋 발주 추천 리스트")
        st.caption(f"기준


