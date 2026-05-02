import streamlit as st
import requests
import os
import shutil
import re

st.set_page_config(page_title="신프로 수집기 (무결점 버전)", layout="wide")
st.title("🎬 신프로의 스마트 실사 수집 엔진 (에러 제로)")

with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key = st.text_input("Pexels API Key", type="password")
    user_gemini_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    video_count = st.slider("영상 개수", 1, 20, 10)
    image_count = st.slider("이미지 개수", 1, 20, 5)
    project_name = st.text_input("프로젝트명 (ZIP 파일명)", "ShinPro_Project")

script_input = st.text_area("📄 대본을 여기에 입력하세요", height=300)

def get_keywords_direct(script, count, type_name, api_key):
    # 가장 빠르고 확실한 1.5-flash 모델 직통 연결 (라이브러리 충돌 없음)
    model = "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
    다음 대본의 흐름을 파악하여 {type_name} 검색용 영어 키워드를 딱 {count}개만 시간 순서대로 뽑아줘. 
    출력 형식은 무조건 '영어키워드_한글요약' 형태로만 해. 다른 말은 절대 쓰지마.
    대본: {script}
    """
    
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    response = requests.post(url, headers=headers, json=data)
    result_json = response.json()
    
    if 'candidates' in result_json:
        text = result_json['candidates'][0]['content']['parts'][0]['text']
        return [k.strip() for k in text.split('\n') if k.strip() and '_' in k]
    else:
        raise Exception(f"새 API 키가 필요합니다! 현재 키 오류: {result_json}")

def download_assets(keywords, asset_type, api_key, folder_name):
    save_path = os.path.abspath(f"{folder_name}/{asset_type}")
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
                
                safe_name = re.sub(r'[\\/*?:"<>|]', "", item.replace(' ', '_'))
                f_name = f"{save_path}/{idx+1:03d}_{safe_name}.{ext}"
                with open(f_name, 'wb') as f:
                    f.write(requests.get(file_url).content)
                st.write(f"✅ {asset_type} 수집 완료: [{idx+1:03d}] {item}")
        except Exception:
            st.write(f"⚠️ {item} 수집 실패")

if st.button("🚀 분석 및 다운로드 시작"):
    if not user_pexels_key or not user_gemini_key:
        st.error("API 키를 모두 입력해주세요.")
    elif not script_input:
        st.warning("대본을 입력해주세요.")
    else:
        with st.spinner("무결점 엔진으로 안전하게 영상 추출 중입니다..."):
            try:
                if os.path.exists(project_name): shutil.rmtree(project_name)
                
                if video_count > 0:
                    st.subheader("🎬 1단계: 영상 소스 작업")
                    v_keys = get_keywords_direct(script_input, video_count, "영상", user_gemini_key)
                    download_assets(v_keys, "Videos", user_pexels_key, project_name)
                
                if image_count > 0:
                    st.subheader("🖼️ 2단계: 이미지 소스 작업")
                    i_keys = get_keywords_direct(script_input, image_count, "사진", user_gemini_key)
                    download_assets(i_keys, "Images", user_pexels_key, project_name)
                
                shutil.make_archive(project_name, 'zip', project_name)
                with open(f"{project_name}.zip", "rb") as f:
                    st.download_button(
                        label="📦 완성된 파일 다운로드 (ZIP)",
                        data=f,
                        file_name=f"{project_name}.zip",
                        mime="application/zip",
                        type="primary"
                    )
                st.success("🎉 모든 작업이 끝났습니다!")
            except Exception as e:
                st.error(f"오류 발생: {e}")
