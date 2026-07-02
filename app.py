import streamlit as st
import pandas as pd
import requests
import time
import io
import re

# ----------------------------------------------------
# 1. API 키 안전하게 불러오기
# ----------------------------------------------------
try:
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    st.error("🔒 보안 설정(Secrets)에 카카오 API 키가 등록되지 않았습니다.")
    st.stop()

def verify_address(address):
    """주소 꼬리표(동, 호수)를 잘라내는 스마트 필터링이 적용된 검증 함수"""
    if pd.isna(address) or str(address).strip() == "":
        return "오류", "입력값 없음", ""
    
    original_addr = str(address).strip()
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    addr_url = "https://dapi.kakao.com/v2/local/search/address.json"
    kw_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    # [스마트 정제 1] 괄호 안의 내용(구주소 등) 통째로 제거
    # 예: "산본로 202 (당동 742)" -> "산본로 202"
    addr_no_bracket = re.sub(r'\(.*?\)', '', original_addr).strip()
    
    # [스마트 정제 2] '동, 호, 층' 등 상세주소 잘라내기
    # "로, 길, 동, 리 + 숫자" 형태까지만 남기고 뒤는 다 버림
    # 예: "금당로 102 102동 703호" -> "금당로 102"
    core_addr_match = re.match(r'(.+(?:로|길|동|리|가)\s*\d+(?:-\d+)?)', addr_no_bracket)
    core_addr = core_addr_match.group(1).strip() if core_addr_match else addr_no_bracket

    # 3단계 그물망 검증 (원본 -> 괄호제거 -> 핵심주소 순으로 찔러봄)
    search_candidates = [original_addr, addr_no_bracket, core_addr]
    
    for query_addr in search_candidates:
        if not query_addr: continue
        try:
            res = requests.get(addr_url, headers=headers, params={"query": query_addr})
            result = res.json()
            
            if result['meta']['total_count'] > 0:
                doc = result['documents'][0]
                road = doc.get('road_address')
                if road:
                    return "검증완료", road['address_name'], road.get('zone_no', '')
                else:
                    return "검증완료", doc['address']['address_name'], doc['address'].get('zip_code', '')
        except:
            pass # 실패하면 다음 후보 주소로 재시도
            
    # 위 3가지 뼈대 주소로도 실패하면, 장소(키워드) API로 아파트명 등 유추 시도
    try:
        kw_res = requests.get(kw_url, headers=headers, params={"query": addr_no_bracket})
        kw_result = kw_res.json()
        if kw_result['meta']['total_count'] > 0:
            suggested = kw_result['documents'][0]
            sugg_addr = suggested.get('road_address_name') or suggested.get('address_name')
            return "💡수정제안", f"[추천 주소] {sugg_addr}", ""
    except:
        pass
        
    return "❌주소오류", "유추 불가 (완전히 없는 주소)", ""

# ----------------------------------------------------
# 2. 웹 화면 UI 구성하기
# ----------------------------------------------------
st.set_page_config(page_title="택배 주소 검증기", page_icon="📦", layout="wide")
st.title("📦 스마트 택배 주소 자동 검증 시스템")
st.markdown("엑셀 파일을 업로드하면 카카오 API를 통해 올바른 표준 도로명 주소를 찾습니다. 동/호수 등 상세 주소로 인한 오류를 자동 보정합니다.")

st.divider()

# 파일 업로드 창
uploaded_file = st.file_uploader("여기에 엑셀 파일을 끌어다 놓거나 클릭해서 업로드하세요.", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.success(f"✅ '{uploaded_file.name}' 파일 업로드 성공!")
        
        if df.shape[1] < 10:
            st.error(f"❌ 파일 열 개수가 부족합니다. (J열 없음)")
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
                col1.metric("전체 건수", f"{total_rows}건")
                col2.metric("✅ 정상 배송", f"{success_cnt}건")
                col3.metric("💡 수정 제안", f"{suggest_cnt}건")
                col4.metric("❌ 완전 오류", f"{error_cnt}건")
                
                st.divider()

                # ------------------------------------------------
                # 4. 확인이 필요한 리스트 출력
                # ------------------------------------------------
                st.subheader("⚠️ 확인 및 수정이 필요한 주소 목록")
                
                df_issue = df[df["검증상태"] != "검증완료"].copy()
                
                if len(df_issue) > 0:
                    display_cols = []
                    for col in df.columns:
                        if "받는분" in col or "수령인" in col or "주문자" in col:
                            if col not in display_cols: display_cols.append(col)
                        if "전화" in col or "연락처" in col:
                            if col not in display_cols: display_cols.append(col)
                            
                    address_col_name = df.columns[9]
                    display_cols.append(address_col_name)
                    display_cols.extend(["검증상태", "표준주소"])
                    
                    final_cols = list(dict.fromkeys([c for c in display_cols if c in df_issue.columns]))
                    
                    st.dataframe(df_issue[final_cols], height=400, use_container_width=True)
                else:
                    st.success("🎉 완벽합니다! 수정할 주소가 한 건도 없습니다.")
                
                # ------------------------------------------------
                # 5. 다운로드
                # ------------------------------------------------
                st.divider()
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)
                
                download_name = uploaded_file.name.replace(".xlsx", "_최종검증.xlsx").replace(".xls", "_최종검증.xlsx")
                
                st.download_button(
                    label="📥 최종 검증 완료된 엑셀 다운로드",
                    data=output,
                    file_name=download_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
    except Exception as e:
        st.error(f"❌ 오류가 발생했습니다: {e}")
