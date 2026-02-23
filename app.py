import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- [모바일 최적화 설정] ---
# layout="centered"가 모바일에서 더 보기 편할 수 있습니다.
st.set_page_config(page_title="GS25 모바일 발주", layout="centered")

# --- [기능 함수 정의] ---
def get_weather_forecast():
    # 실제 API 키가 없다면 데모 데이터를 반환
    return {"temp": 29, "is_rainy": True, "pop": 60}

# --- [메인 화면] ---
st.title("📱 GS25 모바일 발주")

# 1. 상권 및 날씨 설정 (모바일은 사이드바보다 expander가 편함)
with st.expander("🛠️ 매장 환경 및 날씨 설정 (열기)", expanded=True):
    store_type = st.selectbox("상권 선택", ["오피스가", "주택가", "대학가", "유흥가"])
    weather = get_weather_forecast()
    
    col_w1, col_w2 = st.columns(2)
    col_w1.metric("기온", f"{weather['temp']}°C")
    col_w2.metric("상태", "비/눈" if weather['is_rainy'] else "맑음")

# 2. 데이터 업로드
st.write("---")
st.caption("POS 데이터를 선택해주세요")
uploaded_file = st.file_uploader("판매 현황 CSV 파일", type=['csv'])

if uploaded_file:
    # 1. 먼저 그냥(1번째 줄부터) 읽어봅니다.
    try:
        df = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding='cp949')
    
    # 열 이름의 숨겨진 공백(띄어쓰기) 모두 제거
    df.columns = df.columns.str.strip()

    # 2. 만약 1번째 줄에 '상품명'이나 '카테고리'가 없다면? (POS 원본 파일이라서 2번째 줄에 제목이 있는 경우)
    if '카테고리' not in df.columns:
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, header=1)
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, encoding='cp949', header=1)
        
        # 다시 공백 제거
        df.columns = df.columns.str.strip()
        
    # 만약 '행사여부' 등의 이름으로 되어있다면 '행사'로 통일 (에러 방지용)
    if '행사여부' in df.columns: df.rename(columns={'행사여부': '행사'}, inplace=True)
    if '판매량' in df.columns: df.rename(columns={'판매량': '주간판매량'}, inplace=True)
    if '현재 재고' in df.columns: df.rename(columns={'현재 재고': '현재재고'}, inplace=True)
    
    # --- [안전한 발주 로직] ---
    def calculate_mobile_order(row):
        try:
            sales = float(row['주간판매량'])
        except:
            sales = 0.0
            
        try:
            stock = int(row['현재재고'])
        except:
            stock = 0

        avg_sales = sales / 7
        target = avg_sales * 2.5 
        weight = 1.0
        
        # 상권/날씨/행사 가중치 (글자 에러 방지)
        if store_type == "오피스가" and str(row.get('카테고리', '')) in ['도시락', '컵커피']: weight += 0.3
        if weather['is_rainy'] and ("우산" in str(row.get('상품명', '')) or str(row.get('카테고리', '')) == '면류'): weight += 3.0
        
        # 행사 컬럼이 없는 경우를 대비한 안전 장치
        event_val = str(row.get('행사', ''))
        if "1+1" in event_val: weight += 0.5
        elif "2+1" in event_val: weight += 0.3

        return max(0, int((target * weight) - stock))

    # 로직 적용
    df['추천'] = df.apply(calculate_mobile_order, axis=1)

    # --- [모바일 화면 출력] ---
    st.subheader("📦 발주 추천 목록")
    
    edited_df = st.data_editor(
        df[['상품명', '현재재고', '추천']],
        column_config={
            "상품명": st.column_config.TextColumn("상품명", disabled=True),
            "현재재고": st.column_config.NumberColumn("현재재고", disabled=True),
            "추천": st.column_config.NumberColumn("발주확정량", min_value=0, step=1)
        },
        use_container_width=True,
        hide_index=True
    )

    st.write("") 
    
    if st.button("🚀 발주 확정 및 저장", type="primary", use_container_width=True):
        final = edited_df[edited_df['추천'] > 0]
        st.success(f"총 {len(final)}건이 확정되었습니다!")
        
        # CSV 다운로드
        csv = final.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 스마트 발주서 다운로드",
            data=csv,
            file_name="GS25_Smart_Order.csv",
            mime="text/csv",
            use_container_width=True
        )

else:
    st.info("👆 위 버튼을 눌러 POS 판매 현황(CSV) 파일을 올려주세요.")
