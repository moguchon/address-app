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

def get_core_address(addr):
    """카카오 API가 좋아하는 완벽한 뼈대 주소로 변환하는 핵심 엔진"""
    addr = str(addr).strip()
    
    # 1. 괄호 내용(구주소 등) 제거
    addr = re.sub(r'\(.*?\)', '', addr).strip()
    
    # 2. 띄어쓰기 오류 강제 교정 (예: 산본천로 179번길 -> 산본천로179번길)
    addr = re.sub(r'([가-힣]+(?:로|길))\s+(\d+[가-힣]*길)', r'\1\2', addr)
    
    # 3. 명시적인 상세주소(동, 호, 층) 꼬리표 확실하게 잘라내기
    addr = re.sub(r'\s+(?:[가-힣A-Za-z0-9]+동)?\s*(?:지하)?\s*\d+(?:호|층)\b.*$', '', addr)
    
    # 4. '101-201' 처럼 글자 없는 동호수 패턴 제거
    match = re.search(r'([가-힣A-Za-z0-9]+(?:로|길|동|리|가)\s*\d+(?:-\d+)?)\s+\d+-\d+', addr)
    if match:
        addr = match.group(1)
        
    return addr.strip()

def advanced_clean_address(original_addr, standardized_addr, building_name):
    """아파트명 결합 및 101-2301 -> 101동 2301호 정밀 변환"""
    dong_ho = ""
    hyphen_match = re.search(r'(\d+)-(\d+)', original_addr)
    if hyphen_match:
        dong_ho = f"{hyphen_match.group(1)}동 {hyphen_match.group(2)}호"
    else:
        dong_ho_match = re.search(r'(\d+\s*동\s*\d+\s*호)', original_addr)
        if dong_ho_match:
            dong_ho = dong_ho_match.group(1)
        else:
            single_match = re.search(r'(\d+)\s*(?:동|호|층)', original_addr)
            if single_match:
                dong_ho = original_addr[single_match.start():]

    final_addr = standardized_addr
    if building_name and (building_name not in final_addr):
        final_addr = f"{final_addr} {building_name}"
        
    if dong_ho:
        final_addr = f"{final_addr} {dong_ho}"
    else:
        remain_match = re.search(r'(?:로|길|동|리)\s*\d+(?:-\d+)?\s+(.+)', original_addr)
        if remain_match:
            remain_text = remain_match.group(1)
            if building_name not in remain_text:
                final_addr = f"{final_addr} {remain_text}"

    return re.sub(r'\s+', ' ', final_addr).strip()

def verify_address(address):
    """3단계 그물망 검증 함수"""
    if pd.isna(address) or str(address).strip() == "":
        return "오류", "입력값 없음", ""
    
    original_addr = str(address).strip()
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    addr_url = "https://dapi.kakao.com/v2/local/search/address.json"
    kw_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    # 정제 엔진 가동
    core_addr = get_core_address(original_addr)
    addr_no_bracket = re.sub(r'\(.*?\)', '', original_addr).strip()

    # 원본 -> 뼈대주소 -> 괄호제거주소 순으로 3번 찔러봄
    search_candidates = [original_addr, core_addr, addr_no_bracket]
    
    for query_addr in search_candidates:
        if not query_addr: continue
        try:
            res = requests.get(addr_url, headers=headers, params={"query": query_addr})
            result = res.json()
            
            if result['meta']['total_count'] > 0:
                doc = result['documents'][0]
                road = doc.get('road_address')
                
                b_name = road.get('building_name', '') if road else doc['address'].get('building_name', '')
                std_addr = road['address_name'] if road else doc['address']['address_name']
                zip_code = road['zone_no'] if road else doc['address'].get('zip_code', '')
                
                perfect_address = advanced_clean_address(original_addr, std_addr, b_name)
                return "검증완료", perfect_address, zip_code
        except:
            pass
            
    # 장소 검색 유추 단계
    try:
        kw_res = requests.get(kw_url, headers=headers, params={"query": core_addr})
        kw_result = kw_res.json()
        if kw_result['meta']['total_count'] > 0:
            suggested = kw_result['documents'][0]
            sugg_addr = suggested.get('road_address_name') or suggested.get('address_name')
            b_name = suggested.get('place_name', '')
            
            perfect_address = advanced_clean_address(original_addr, sugg_addr, b_name)
            return "💡수정제안", f"[추천] {perfect_address}", ""
    except:
        pass
        
    return "❌주소오류", "유추 불가 (완전히 없는 주소)", ""

# ----------------------------------------------------
# 2. 웹 화면 UI 구성하기
# ----------------------------------------------------
st.set_page_config(page_title="스마트 택배 주소 검증기", page_icon="📦", layout="wide")
st.title("📦 스마트 택배 주소 자동 검증 시스템")
st.markdown("엑셀 파일의 주소를 기반으로 띄어쓰기 오류를 자동 교정하고, 건물명(아파트명)과 동/호수를 완벽하게 결합해 줍니다.")

st.divider()

uploaded_file = st.file_uploader("여기에 엑셀 파일을 업로드하세요.", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        st.success(f"✅ '{uploaded_file.name}' 파일 로드 완료!")
        
        if df.shape[1] < 10:
            st.error("❌ 파일 열 개수가 부족합니다. (J열 없음)")
        else:
            if st.button("🚀 주소 변환 및 검증 시작", type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_list, corrected_address_list, zipcode_list = [], [], []
                total_rows = len(df)
                
                for index, row in df.iterrows():
                    progress_percentage = int(((index + 1) / total_rows) * 100)
                    progress_bar.progress(progress_percentage)
                    
                    original_addr = df.iloc[index, 9]
                    status_text.text(f"처리 중... [{index+1}/{total_rows}] : {original_addr}")
                    
                    status, corrected_addr, zip_code = verify_address(original_addr)
                    status_list.append(status)
                    corrected_address_list.append(corrected_addr)
                    zipcode_list.append(zip_code)
                    
                    time.sleep(0.05) 
                
                df["검증상태"] = status_list
                df["표준주소"] = corrected_address_list
                df["우편번호"] = zipcode_list
                
                status_text.text("🎉 주소 변환 및 검증이 모두 완료되었습니다!")
                
                st.subheader("📊 변환 결과 요약")
                success_cnt = len(df[df["검증상태"] == "검증완료"])
                suggest_cnt = len(df[df["검증상태"] == "💡수정제안"])
                error_cnt = len(df[df["검증상태"] == "❌주소오류"])
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("전체 건수", f"{total_rows}건")
                col2.metric("✅ 변환 완료", f"{success_cnt}건")
                col3.metric("💡 수정 제안", f"{suggest_cnt}건")
                col4.metric("❌ 완전 오류", f"{error_cnt}건")
                
                st.divider()
                st.subheader("⚠️ 확인 및 수정이 필요한 주소 목록")
                df_issue = df[df["검증상태"] != "검증완료"].copy()
                
                if len(df_issue) > 0:
                    display_cols = []
                    for col in df.columns:
                        if any(k in col for k in ["받는분", "수령인", "주문자", "전화", "연락처"]):
                            if col not in display_cols: display_cols.append(col)
                    address_col_name = df.columns[9]
                    display_cols.append(address_col_name)
                    display_cols.extend(["검증상태", "표준주소"])
                    
                    final_cols = list(dict.fromkeys([c for c in display_cols if c in df_issue.columns]))
                    st.dataframe(df_issue[final_cols], height=400, use_container_width=True)
                else:
                    st.success("🎉 모든 주소가 완벽하게 변환되었습니다!")
                
                st.divider()
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)
                
                st.download_button(
                    label="📥 최종 정제된 엑셀 다운로드",
                    data=output,
                    file_name=uploaded_file.name.replace(".xlsx", "_완벽정제.xlsx").replace(".xls", "_완벽정제.xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
