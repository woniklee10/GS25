import streamlit as st
import pandas as pd
import requests
from geopy.geocoders import Nominatim
import numpy as np

# --- [1. 기본 설정] ---
st.set_page_config(page_title="GS25 스마트 발주", layout="centered")

# --- [2. 기능 함수 정의] ---
def get_location(store_name):
    try:
        geolocator = Nominatim(user_agent="gs25_manager_final_v7")
        # 한국 주소 검색
        loc = geolocator.geocode(f"{store_name}, South Korea")
        if loc: return loc.latitude, loc.longitude, loc.address
        return None, None, None
    except: return None, None, None

def get_forecast(lat, lon, days_later=1):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,precipitation_sum&timezone=auto"
        res = requests.get(url).json()
        idx = days_later
        if 'daily' in res and len(res['daily']['temperature_2m_max']) > idx:
            t_max = res['daily']['temperature_2m_max'][idx]
            rain = res['daily']['precipitation_sum'][idx]
            return {"temp": t_max, "rain_mm": rain, "is_rainy": rain > 5.0}
        return {"temp": 25, "rain_mm": 0, "is_rainy": False}
    except:
        return {"temp": 25, "rain_mm": 0, "is_rainy": False}

# --- [3. 메인 화면 UI] ---
st.title("📊 GS25 매출비교 기반 스마트 발주")
st.markdown("매출비교(PDF/엑셀) 파일을 업로드하면 **조회기간의 판매량**을 분석해 발주를 제안합니다.")

# (1) 점포 및 날씨 설정
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

# (2) 데이터 기간 설정
st.write("---")
col_d1, col_d2 = st.columns(2)
with col_d1:
    data_days = st.number_input("조회 기간(일)", min_value=1, value=7, help="매출비교 리포트가 7일치면 7을 입력")
with col_d2:
    target_stock_days = st.number_input("목표 재고 일수", min_value=1.0, value=2.5, step=0.5)

# (3) 파일 업로드 버튼 (이 부분이 없어서 에러가 났던 것입니다!)
uploaded_file = st.file_uploader("매출비교 파일 업로드 (xlsx/csv)", type=['csv', 'xlsx'])

# --- [4. 데이터 분석 및 결과] ---
if uploaded_file:
    # A. 파일 읽기 (엑셀/CSV 자동 판별)
    if uploaded_file.name.endswith('.xlsx'):
        df_raw = pd.read_excel(uploaded_file, header=1)
    else:
        try:
            df_raw = pd.read_csv(uploaded_file, header=1)
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            df_raw = pd.read_csv(uploaded_file, header=1, encoding='cp949')

    # B. 컬럼 정리 (공백/줄바꿈 제거)
    df_raw.columns = [str(c).replace(" ", "").replace("\n", "") for c in df_raw.columns]
    
    df = pd.DataFrame()
    
    # C. 데이터 추출
    # 1. 상품명
    df['상품명'] = df_raw.iloc[:, 0]
    
    # 2. 카테고리
    if '카테고리' in df_raw.columns:
        df['카테고리'] = df_raw['카테고리']
    elif '등급' in df_raw.columns:
        df['카테고리'] = df_raw['등급']
    else:
        df['카테고리'] = '기타'

    # 3. 판매수량 (중복된 열 중 첫 번째 것 사용)
    sales_cols = [c for c in df_raw.columns if '판매수량' in c]
    if len(sales_cols) > 0:
        df['기간판매량'] = df_raw[sales_cols[0]]
    else:
        st.error("🚨 '판매수량' 열을 찾을 수 없습니다. 파일 양식을 확인해주세요.")
        st.stop()
        
    # 4. 재고수량
    stock_cols = [c for c in df_raw.columns if '재고' in c]
    if len(stock_cols) > 0:
        df['현재재고'] = df_raw[stock_cols[0]]
    else:
        df['현재재고'] = 0

    # 5. 행사 정보
    event_cols = [c for c in df_raw.columns if '행사' in c]
    if len(event_cols) > 0:
        df['행사'] = df_raw[event_cols[0]]
    else:
        df['행사'] = ''

    # D. 숫자 변환 (콤마 제거)
    def clean_num(x):
        try:
            if pd.isna(x) or str(x).strip() == '': return 0
            return float(str(x).replace(',', ''))
        except:
            return 0

    df['기간판매량'] = df['기간판매량'].apply(clean_num)
    df['현재재고'] = df['현재재고'].apply(clean_num)
    
    # 상품명이 없는 빈 줄 제거
    df = df[df['상품명'].notna()]
    df = df[df['상품명'] != '']

    # E. 발주 로직 계산
    def calculate_order(row):
        daily_sales = row['기간판매량'] / data_days
        target = daily_sales * target_stock_days
        weight = 1.0
        
        name = str(row['상품명'])
        cat = str(row['카테고리'])
        
        # 날씨 가중치
        if weather['temp'] >= 28:
            if '음료' in cat or '아이스' in name or '빙과' in name: weight += 0.3
        if weather['is_rainy']:
            if '우산' in name: weight += 4.0
            if '면류' in cat or '국물' in name: weight += 0.2
        
        # 행사 가중치
        if '1+1' in str(row['행사']): weight += 0.5
        elif '2+1' in str(row['행사']): weight += 0.3
        
        needed = (target * weight) - row['현재재고']
        return max(0, int(needed))

    df['추천발주'] = df.apply(calculate_order, axis=1)

    # F. 결과 출력
    st.subheader("📋 발주 추천 리스트")
    st.caption(f"기준: 최근 {data_days}일 판매 / {target_stock_days}일치 재고")

    final_df = df[df['추천발주'] > 0].sort_values('추천발주', ascending=False)
    
    cols_to_show = ['상품명', '기간판매량', '현재재고', '추천발주']
    if '행사' in df.columns: cols_to_show.append('행사')

    edited_df = st.data_editor(
        final_df[cols_to_show],
        column_config={
            "상품명": st.column_config.TextColumn("상품명"),
            "기간판매량": st.column_config.NumberColumn("기간판매", format="%d개"),
            "현재재고": st.column_config.NumberColumn("현재재고", format="%d개"),
            "추천발주": st.column_config.NumberColumn("발주확정", min_value=0, step=1)
        },
        use_container_width=True,
        hide_index=True
    )

    st.write("")
    if st.button("💾 발주서(CSV) 다운로드", type="primary", use_container_width=True):
        csv = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 파일 받기", csv, "Order.csv", "text/csv")

else:
    st.info("👆 위 버튼을 눌러 파일을 업로드해주세요.")





