import streamlit as st
import pandas as pd
import requests
from geopy.geocoders import Nominatim
import numpy as np

# --- [설정] ---
st.set_page_config(page_title="GS25 매출비교 기반 발주", layout="centered")

# --- [함수: 위치 및 날씨] ---
def get_location(store_name):
    try:
        geolocator = Nominatim(user_agent="gs25_manager_app_v4")
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

# 2. 데이터 기간 설정
st.write("---")
col_d1, col_d2 = st.columns(2)
with col_d1:
    data_days = st.number_input("조회 기간(일)", min_value=1, value=7, help="매출비교 리포트가 7일치면 7을 입력")
with col_d2:
    target_stock_days = st.number_input("목표 재고 일수", min_value=1.0, value=2.5, step=0.5)

# 3. 파일 업로드
uploaded_file = st.file_uploader("매출비교 파일 업로드 (xlsx/csv)", type=['csv', 'xlsx'])

if uploaded_file:
    try:
        # --- [1. 파일 읽기] ---
        # 엑셀/CSV 구분 및 2번째 줄(header=1) 읽기 시도
        if uploaded_file.name.endswith('.xlsx'):
            df_raw = pd.read_excel(uploaded_file, header=1)
        else:
            try:
                df_raw = pd.read_csv(uploaded_file, header=1)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df_raw = pd.read_csv(uploaded_file, header=1, encoding='cp949')

        # --- [2. 데이터 전처리] ---
        # 컬럼명 공백 제거 (예: " 판매수량 " -> "판매수량")
        df_raw.columns = [str(c).replace(" ", "").replace("\n", "") for c in df_raw.columns]
        
        df = pd.DataFrame()
        
        # (1) 상품명 추출



