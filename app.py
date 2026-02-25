import streamlit as st
import pandas as pd
import requests
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta

# --- [설정] ---
st.set_page_config(page_title="GS25 스마트 발주 (위치기반)", layout="centered")

# --- [함수 1: 점포 위치 찾기] ---
def get_location(store_name):
    try:
        geolocator = Nominatim(user_agent="gs25_manager_app")
        # 한국 검색을 위해 뒤에 'South Korea'를 붙여줌
        loc = geolocator.geocode(f"{store_name}, South Korea")
        if loc:
            return loc.latitude, loc.longitude, loc.address
        return None, None, None
    except:
        return None, None, None

# --- [함수 2: 해당 위치의 특정 날짜 날씨 예보 가져오기 (Open-Meteo)] ---
def get_forecast(lat, lon, days_later=1):
    try:
        # 무료 날씨 API (Open-Meteo) 호출
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,precipitation_sum&timezone=auto"
        res = requests.get(url).json()
        
        # days_later: 1이면 내일, 2면 모레
        target_idx = days_later 
        
        temp_max = res['daily']['temperature_2m_max'][target_idx]
        rain_sum = res['daily']['precipitation_sum'][target_idx]
        
        is_rainy = rain_sum > 5.0 # 5mm 이상 오면 비로 간주
        
        return {
            "temp": temp_max,
            "rain_mm": rain_sum,
            "is_rainy": is_rainy
        }
    except:
        # 에러 시 기본값 (서울 평균)
        return {"temp": 25, "rain_mm": 0, "is_rainy": False}

# --- [메인 화면] ---
st.title("🗺️ GS25 위치 기반 스마트 발주")

with st.expander("🏪 점포 설정 및 날씨 조회 (열기)", expanded=True):
    # 1. 점포명 입력
    col_s1, col_s2 = st.columns([2, 1])
    input_store = col_s1.text_input("점포명 또는 지역명 입력", value="GS25 강남역점")
    target_day = col_s2.selectbox("입고 예정일", ["내일 도착", "모레 도착"])
    
    # 날짜 계산 (1=내일, 2=모레)
    day_offset = 1 if target_day == "내일 도착" else 2
    
    # 2. 위치 및 날씨 검색
    if input_store:
        lat, lon, addr = get_location(input_store)
        
        if lat:
            st.success(f"📍 위치 확인: {addr}")
            weather = get_forecast(lat, lon, day_offset)
            
            # 날씨 정보 표시
            c1, c2, c3 = st.columns(3)
            c1.metric("예상 최고기온", f"{weather['temp']}°C")
            c2.metric("예상 강수량", f"{weather['rain_mm']}mm")
            w_status = "☔ 비/눈" if weather['is_rainy'] else "☀️ 맑음/흐림"
            c3.metric("날씨 상태", w_status)
            
            st.caption(f"※ 위 날씨는 **{target_day}** 기준 예보입니다.")
        else:
            st.error("위치를 찾지 못했습니다. '서울 강남구' 처럼 지역명으로 입력해보세요.")
            weather = {"temp": 25, "rain_mm": 0, "is_rainy": False} # 기본값
    else:
        weather = {"temp": 25, "rain_mm": 0, "is_rainy": False}


# --- [파일 업로드 및 분석] ---
st.write("---")
uploaded_file = st.file_uploader("POS 판매 데이터 업로드 (CSV)", type=['csv'])

if uploaded_file:
    # --- [CSV 자동 감지 로직 (이전과 동일)] ---
    try:
        df = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding='cp949')
    
    df.columns = df.columns.str.strip()

    if '카테고리' not in df.columns:
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, header=1)
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, encoding='cp949', header=1)
        df.columns = df.columns.str.strip()
        
    if '행사여부' in df.columns: df.rename(columns={'행사여부': '행사'}, inplace=True)
    if '판매량' in df.columns: df.rename(columns={'판매량': '주간판매량'}, inplace=True)
    if '현재 재고' in df.columns: df.rename(columns={'현재 재고': '현재재고'}, inplace=True)

    # --- [스마트 발주 계산 로직 (날씨 반영)] ---
    def calculate_smart_order(row):
        try:
            sales = float(row.get('주간판매량', 0))
        except: sales = 0.0
        
        try:
            stock = int(row.get('현재재고', 0))
        except: stock = 0
            
        avg_sales = sales / 7
        target = avg_sales * 2.5
        weight = 1.0
        
        # [NEW] 실시간 위치 기반 날씨 로직 적용
        cat = str(row.get('카테고리', ''))
        name = str(row.get('상품명', ''))
        
        # 1. 기온 반영 (더우면 음료/빙과류 증가)
        if weather['temp'] >= 28:
            if cat in ['음료', '유제품', '아이스크림']: weight += 0.3
            if '얼음' in name: weight += 0.5
            
        # 2. 강수량 반영 (비 오면 우산/막걸리/전류/라면 증가)
        if weather['is_rainy']:
            if "우산" in name: weight += 4.0   # 우산은 4배 발주
            if cat == '면류': weight += 0.2    # 라면
            if cat in ['안주류', '주류']: weight += 0.15 # 파전/막걸리 효과
            
        # 3. 행사 반영
        event = str(row.get('행사', ''))
        if "1+1" in event: weight += 0.5
        elif "2+1" in event: weight += 0.3

        return max(0, int((target * weight) - stock))

    df['추천'] = df.apply(calculate_smart_order, axis=1)

    # --- [결과 화면] ---
    st.subheader(f"📋 {target_day} 날씨 맞춤 발주 제안")
    
    if weather['is_rainy']:
        st.info("☔ 비 예보가 있어 우산과 국물 요리 발주량을 늘렸습니다.")
    if weather['temp'] >= 28:
        st.warning("🔥 더운 날씨가 예상되어 음료/빙과류 재고를 확보합니다.")

    edited_df = st.data_editor(
        df[['상품명', '현재재고', '추천']],
        column_config={
            "상품명": st.column_config.TextColumn("상품명", disabled=True),
            "현재재고": st.column_config.NumberColumn("현재재고", disabled=True),
            "추천": st.column_config.NumberColumn("발주량", min_value=0, step=1)
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.write("")
    if st.button("🚀 발주 확정 및 파일 저장", type="primary", use_container_width=True):
        final = edited_df[edited_df['추천'] > 0]
        csv = final.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 발주서 다운로드", csv, "Order_Result.csv", "text/csv", use_container_width=True)

else:
    st.info("👆 CSV 파일을 업로드해주세요.")

