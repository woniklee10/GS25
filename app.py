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
    try:
        df = pd.read_csv(uploaded_file)
    except UnicodeDecodeError:
        uploaded_file.seek(0)  # 👈 추가된 부분: 책갈피를 다시 맨 처음으로 되돌립니다!
        df = pd.read_csv(uploaded_file, encoding='cp949')
        
    # --- [발주 로직] ---
    def calculate_mobile_order(row):
        avg_sales = row['주간판매량'] / 7
        target = avg_sales * 2.5 # 모바일용 안전재고율 소폭 상향
        weight = 1.0
        
        # 상권/날씨/행사 가중치 (이전과 동일)
        if store_type == "오피스가" and row['카테고리'] in ['도시락', '컵커피']: weight += 0.3
        if weather['is_rainy'] and ("우산" in row['상품명'] or row['카테고리'] == '면류'): weight += 3.0
        if "1+1" in str(row['행사']): weight += 0.5

        return max(0, int((target * weight) - row['현재재고']))

    df['추천'] = df.apply(calculate_mobile_order, axis=1)

    # --- [모바일용 리스트 뷰] ---
    st.subheader("📦 발주 추천 목록")
    
    # 모바일에서는 표(Table)보다 카드 형태나 필요한 정보만 보여주는 것이 좋습니다.
    # 데이터 에디터는 화면을 많이 차지하므로 필요한 컬럼만 최소화합니다.
    
    edited_df = st.data_editor(
        df[['상품명', '현재재고', '추천']],
        column_config={
            "상품명": st.column_config.TextColumn("상품명", disabled=True),
            "현재재고": st.column_config.NumberColumn("재고", disabled=True, format="%d개"),
            "추천": st.column_config.NumberColumn("발주량", min_value=0, step=1, help="수정가능")
        },
        use_container_width=True, # 화면 너비 꽉 채우기
        hide_index=True
    )

    # 하단 고정 버튼 느낌을 주기 위한 여백
    st.write("") 
    
    if st.button("🚀 발주 확정 및 저장", type="primary", use_container_width=True):
        final = edited_df[edited_df['추천'] > 0]
        st.success(f"총 {len(final)}건 확정됨")
        
        # CSV 다운로드
        csv = final.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 발주서 파일 받기",
            data=csv,
            file_name="order_mobile.csv",
            mime="text/csv",
            use_container_width=True
        )

else:

    st.info("👆 위에서 파일을 업로드하면 분석이 시작됩니다.")

