import streamlit as st
import pandas as pd
import requests
import time
import io

# ----------------------------------------------------
# 1. API 키 안전하게 불러오기 (스트림릿 시크릿 저장소 활용)
# ----------------------------------------------------
try:
    KAKAO_API_KEY = st.secrets["KAKAO_API_KEY"]
except:
    st.error("🔒 보안 설정(Secrets)에 카카오 API 키가 등록되지 않았습니다.")
    st.stop()

def verify_address(address):
    """카카오 로컬 API를 이용해 주소를 검증하는 함수"""
    if pd.isna(address) or str(address).strip() == "":
        return "오류", "입력값 없음", ""
    
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": str(address)}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        result = response.json()
        
        if result['meta']['total_count'] > 0:
            doc = result['documents'][0]
            road_address = doc.get('road_address')
            
            if road_address:
                return "검증완료", road_address['address_name'], road_address.get('zone_no', '')
            else:
                return "검증완료", doc['address']['address_name'], doc['address'].get('zip_code', '')
        else:
            return "주소오류", "검색 결과 없음", ""
    except Exception as e:
        return "시스템오류", str(e), ""

# ----------------------------------------------------
# 2. 웹 화면 UI 구성하기
# ----------------------------------------------------
st.set_page_config(page_title="택배 주소 검증기", page_icon="📦")
st.title("📦 택배 주소 자동 검증 시스템")
st.markdown("엑셀 파일을 업로드하면 카카오 API를 통해 올바른 **표준 도로명 주소**와 **5자리 우편번호**를 찾아줍니다. (J열 기준)")

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
            # 시작 버튼
            if st.button("🚀 주소 유효성 검증 시작", type="primary"):
                
                # 진행 상황 표시 바(Bar)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_list, corrected_address_list, zipcode_list = [], [], []
                total_rows = len(df)
                
                for index, row in df.iterrows():
                    # 진행률 업데이트
                    progress_percentage = int(((index + 1) / total_rows) * 100)
                    progress_bar.progress(progress_percentage)
                    
                    original_addr = df.iloc[index, 9] # J열 데이터
                    status_text.text(f"진행 중... [{index+1}/{total_rows}] : {original_addr}")
                    
                    status, corrected_addr, zip_code = verify_address(original_addr)
                    status_list.append(status)
                    corrected_address_list.append(corrected_addr)
                    zipcode_list.append(zip_code)
                    
                    time.sleep(0.05) # API 과부하 방지
                
                # 결과 저장
                df["검증상태"] = status_list
                df["표준주소"] = corrected_address_list
                df["우편번호"] = zipcode_list
                
                status_text.text("🎉 모든 주소 검증이 완료되었습니다!")
                st.balloons() # 축하 애니메이션
                
                # 미리보기 제공
                st.subheader("📊 검증 결과 미리보기")
                st.dataframe(df.tail())
                
                # 엑셀 다운로드 버튼 생성 (메모리 버퍼 사용)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)
                
                download_name = uploaded_file.name.replace(".xlsx", "_검증완료.xlsx").replace(".xls", "_검증완료.xlsx")
                
                st.download_button(
                    label="📥 검증 완료된 엑셀 파일 다운로드",
                    data=output,
                    file_name=download_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
    except Exception as e:
        st.error(f"❌ 파일을 읽는 중 오류가 발생했습니다: {e}")
