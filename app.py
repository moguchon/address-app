import streamlit as st
import pandas as pd
import requests
import time
import io

# ----------------------------------------------------
# 1. API 키 안전하게 불러오기
# ----------------------------------------------------
try:
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    st.error("🔒 보안 설정(Secrets)에 카카오 API 키가 등록되지 않았습니다.")
    st.stop()

def verify_address(address):
    """카카오 로컬 API를 이용해 주소를 검증하고, 실패 시 유사 주소를 추천하는 함수"""
    if pd.isna(address) or str(address).strip() == "":
        return "오류", "입력값 없음", ""
    
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    
    # [1단계] 정확한 주소 매칭 시도
    addr_url = "https://dapi.kakao.com/v2/local/search/address.json"
    params = {"query": str(address)}
    
    try:
        response = requests.get(addr_url, headers=headers, params=params)
        result = response.json()
        
        if result['meta']['total_count'] > 0:
            doc = result['documents'][0]
            road_address = doc.get('road_address')
            
            if road_address:
                return "검증완료", road_address['address_name'], road_address.get('zone_no', '')
            else:
                return "검증완료", doc['address']['address_name'], doc['address'].get('zip_code', '')
        
        else:
            # [2단계] 검색 결과가 없으면 '키워드 장소 검색'으로 오탈자/아파트명 유추
            kw_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            kw_response = requests.get(kw_url, headers=headers, params=params)
            kw_result = kw_response.json()
            
            if kw_result['meta']['total_count'] > 0:
                suggested = kw_result['documents'][0]
                # 장소 검색은 road_address_name 우선, 없으면 address_name 사용
                sugg_addr = suggested.get('road_address_name') or suggested.get('address_name')
                return "💡수정제안", f"[추천 주소] {sugg_addr}", ""
            else:
                return "❌주소오류", "유추 불가 (완전히 없는 주소)", ""
                
    except Exception as e:
        return "시스템오류", str(e), ""

# ----------------------------------------------------
# 2. 웹 화면 UI 구성하기
# ----------------------------------------------------
st.set_page_config(page_title="택배 주소 검증기", page_icon="📦", layout="wide")
st.title("📦 택배 주소 자동 검증 시스템")
st.markdown("엑셀 파일을 업로드하면 카카오 API를 통해 올바른 표준 도로명 주소를 찾고, 오탈자가 있는 주소는 유사한 장소로 추천해 줍니다.")

st.divider()

# 파일 업로드 창
uploaded_file = st.file_uploader("여기에 엑셀 파일을 끌어다 놓거나 클릭해서 업로드하세요.", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.success(f"✅ '{uploaded_file.name}' 파일이 성공적으로 업로드되었습니다.")
        
        if df.shape[1] < 10:
            st.error(f"❌ 파일의 열 개수가 부족합니다. (현재 {df.shape[1]}개 열 존재, 검증할 J열이 없습니다.)")
        else:
            if st.button("🚀 주소 유효성 검증 시작", type="primary"):
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_list, corrected_address_list, zipcode_list = [], [], []
                total_rows = len(df)
                
                for index, row in df.iterrows():
                    progress_percentage = int(((index + 1) / total_rows) * 100)
                    progress_bar.progress(progress_percentage)
                    
                    original_addr = df.iloc[index, 9] # J열 데이터
                    status_text.text(f"검증 중... [{index+1}/{total_rows}] : {original_addr}")
                    
                    status, corrected_addr, zip_code = verify_address(original_addr)
                    status_list.append(status)
                    corrected_address_list.append(corrected_addr)
                    zipcode_list.append(zip_code)
                    
                    time.sleep(0.05) 
                
                # 결과 반영
                df["검증상태"] = status_list
                df["표준주소"] = corrected_address_list
                df["우편번호"] = zipcode_list
                
                status_text.text("🎉 모든 주소 검증이 완료되었습니다!")
                
                # ------------------------------------------------
                # 3. 결과 요약 대시보드
                # ------------------------------------------------
                st.subheader("📊 검증 결과 요약")
                
                success_cnt = len(df[df["검증상태"] == "검증완료"])
                suggest_cnt = len(df[df["검증상태"] == "💡수정제안"])
                error_cnt = len(df[df["검증상태"] == "❌주소오류"])
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("전체 주소", f"{total_rows}건")
                col2.metric("✅ 정상 배송 가능", f"{success_cnt}건")
                col3.metric("💡 확인 필요 (수정제안)", f"{suggest_cnt}건")
                col4.metric("❌ 완전 오류 (확인불가)", f"{error_cnt}건")
                
                st.divider()

                # ------------------------------------------------
                # 4. 확인이 필요한 오류/추천 리스트업 (핵심 정보만)
                # ------------------------------------------------
                st.subheader("⚠️ 확인 및 수정이 필요한 주소 목록")
                
                # 검증완료가 아닌 데이터만 필터링
                df_issue = df[df["검증상태"] != "검증완료"].copy()
                
                if len(df_issue) > 0:
                    # 엑셀 열 이름 동적 찾기 (받는분, 전화번호 등)
                    display_cols = []
                    for col in df.columns:
                        if "받는분" in col or "수령인" in col or "주문자" in col:
                            if col not in display_cols: display_cols.append(col)
                        if "전화" in col or "연락처" in col:
                            if col not in display_cols: display_cols.append(col)
                            
                    # J열(원본 주소), 상태, 표준주소(추천결과) 강제 추가
                    address_col_name = df.columns[9]
                    display_cols.append(address_col_name)
                    display_cols.extend(["검증상태", "표준주소"])
                    
                    # 중복 제거 및 리스트 정렬
                    final_cols = list(dict.fromkeys([c for c in display_cols if c in df_issue.columns]))
                    
                    # 수백 건이어도 스크롤 박스 안에서 편하게 볼 수 있도록 세팅 (높이 400px 지정)
                    st.dataframe(df_issue[final_cols], height=400, use_container_width=True)
                else:
                    st.success("🎉 완벽합니다! 수정할 주소가 한 건도 없습니다.")
                
                # 다운로드 기능
                st.divider()
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)
                
                download_name = uploaded_file.name.replace(".xlsx", "_검증완료.xlsx").replace(".xls", "_검증완료.xlsx")
                
                st.download_button(
                    label="📥 최종 검증 완료된 엑셀 다운로드 (전체 내역 포함)",
                    data=output,
                    file_name=download_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
    except Exception as e:
        st.error(f"❌ 파일을 읽고 처리하는 중 오류가 발생했습니다: {e}")
