import streamlit as st
import requests
import os
import shutil
import re
from google import genai

st.set_page_config(page_title="신프로 캡컷 소스 공급기", layout="wide")
st.title("🎬 신프로의 CapCut 스튜디오 소스 공급기 (하이브리드)")

with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key = st.text_input("Pexels API Key", type="password")
    user_gemini_key = st.text_input("Gemini API Key (자동 모드용)", type="password")
    st.divider()
    project_name = st.text_input("프로젝트명 (ZIP 파일명)", "ShinPro_CapCut_Source")

st.markdown("### ⚙️ 작업 방식 선택")
mode = st.radio(
    "구글 API 에러 발생 시 B플랜을 선택하세요.", 
    ["A플랜: 대본 넣고 자동 추출 (Gemini API)", "B플랜: 키워드 직접 입력 (API 없이 즉시 다운로드)"]
)

# UI 구성
if "A플랜" in mode:
    script_input = st.text_area("📄 대본을 여기에 입력하세요", height=200)
    col1, col2 = st.columns(2)
    with col1: video_count = st.slider("영상 개수", 1, 20, 10)
    with col2: image_count = st.slider("이미지 개수", 1, 20, 5)
else:
    st.info("💡 챗GPT나 Gemini에게 키워드를 뽑아달라고 한 뒤, 아래에 한 줄에 하나씩 붙여넣으세요. (예: `기름_Oil`, `비행기_Airplane`)")
    manual_video_keys = st.text_area("🎥 영상 검색용 키워드 (한 줄에 하나씩)", height=150)
    manual_image_keys = st.text_area("🖼️ 이미지 검색용 키워드 (한 줄에 하나씩)", height=100)

def extract_keywords_with_genai(script, count, type_name, api_key):
    client = genai.Client(api_key=api_key)
    prompt = f"다음 대본을 읽고 {type_name} 검색용 영어 키워드 {count}개를 '영어키워드_한글의미' 형태로만 추출해. 다른 설명은 절대 금지.\n대본: {script}"
    response = client.models.generate_content(
        model='gemini-2.0-flash', # 구글의 가장 최신 기본 모델
        contents=prompt
    )
    return [k.strip() for k in response.text.split('\n') if k.strip() and '_' in k]

def download_assets(keywords, asset_type, api_key, folder_name):
    # 캡컷 스튜디오에 맞게 폴더명 지정 (Videos -> 영상, Images -> 이미지)
    save_path = os.path.abspath(f"{folder_name}/{'영상' if asset_type == 'Videos' else '이미지'}")
    if not os.path.exists(save_path): os.makedirs(save_path)
    headers = {"Authorization": api_key}
    
    for idx, item in enumerate(keywords):
        if not item.strip(): continue
        query = item.split('_')[0] if '_' in item else item
        
        base_url = "https://api.pexels.com/videos/search" if asset_type == "Videos" else "https://api.pexels.com/v1/search"
        url = f"{base_url}?query={query}&orientation=landscape&per_page=1"
        try:
            res = requests.get(url, headers=headers).json()
            items = res.get('videos') if asset_type == "Videos" else res.get('photos')
            if items:
                file_url = items[0]['video_files'][0]['link'] if asset_type == "Videos" else items[0]['src']['original']
                ext = "mp4" if asset_type == "Videos" else "jpg"
                
                # 캡컷 스튜디오 넘버링 형식 (001_키워드.mp4)
                safe_name = re.sub(r'[\\/*?:"<>|]', "", item.replace(' ', '_'))
                f_name = f"{save_path}/{idx+1:03d}_{safe_name}.{ext}"
                with open(f_name, 'wb') as f:
                    f.write(requests.get(file_url).content)
                st.write(f"✅ {asset_type} 수집: [{idx+1:03d}] {item}")
        except Exception:
            st.write(f"⚠️ {item} 수집 실패")

if st.button("🚀 캡컷 소스 다운로드 시작"):
    if not user_pexels_key:
        st.error("Pexels API Key는 필수입니다.")
    else:
        with st.spinner("캡컷 스튜디오용 폴더를 제작하고 있습니다..."):
            try:
                if os.path.exists(project_name): shutil.rmtree(project_name)
                
                if "A플랜" in mode:
                    if not user_gemini_key or not script_input:
                        st.error("Gemini API Key와 대본을 입력해주세요.")
                        st.stop()
                    st.subheader("🎬 A플랜: 자동 추출 및 다운로드")
                    v_keys = extract_keywords_with_genai(script_input, video_count, "영상", user_gemini_key)
                    i_keys = extract_keywords_with_genai(script_input, image_count, "사진", user_gemini_key)
                else:
                    st.subheader("🎬 B플랜: 다이렉트 다운로드")
                    v_keys = [k for k in manual_video_keys.split('\n') if k.strip()]
                    i_keys = [k for k in manual_image_keys.split('\n') if k.strip()]

                if v_keys: download_assets(v_keys, "Videos", user_pexels_key, project_name)
                if i_keys: download_assets(i_keys, "Images", user_pexels_key, project_name)
                
                shutil.make_archive(project_name, 'zip', project_name)
                with open(f"{project_name}.zip", "rb") as f:
                    st.download_button(
                        label="📦 완성된 캡컷 소스 다운로드 (ZIP)",
                        data=f,
                        file_name=f"{project_name}.zip",
                        mime="application/zip",
                        type="primary"
                    )
                st.success("🎉 다운로드가 완료되었습니다! 이제 압축을 풀고 캡컷 스튜디오에 넣으세요.")
            except Exception as e:
                st.error(f"오류 발생: {e}")
