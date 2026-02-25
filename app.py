if uploaded_file:
    # --- [수정된 부분] 2번째 줄(header=1)부터 읽으라고 명령! ---
    try:
        # header=1을 추가하면 두 번째 줄을 제목으로 인식합니다.
        df = pd.read_csv(uploaded_file, header=1)
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding='cp949', header=1)

    # 빈칸(NaN) 정리 (행사 정보가 없으면 빈칸으로 처리)
    df = df.fillna('')
    
    # --- [기존 발주 로직] ---
    def calculate_mobile_order(row):
        # 주간판매량이 숫자가 아니라면 0으로 처리 (에러 방지용)
        try:
            sales = float(row['주간판매량'])
        except:
            sales = 0
            
        try:
            stock = int(row['현재재고'])
        except:
            stock = 0

        avg_sales = sales / 7
        target = avg_sales * 2.5 
        weight = 1.0
        
        # 상권/날씨/행사 가중치
        if store_type == "오피스가" and row['카테고리'] in ['도시락', '컵커피']: weight += 0.3
        if weather['is_rainy'] and ("우산" in str(row['상품명']) or str(row['카테고리']) == '면류'): weight += 3.0
        if "1+1" in str(row['행사']): weight += 0.5

        return max(0, int((target * weight) - stock))

    df['추천'] = df.apply(calculate_mobile_order, axis=1)

    # --- [모바일용 리스트 뷰 (이하 기존과 동일)] ---





