import streamlit as st
import requests
import os
import shutil
import time
import re
import concurrent.futures
import google.generativeai as genai

st.set_page_config(page_title="신프로 수집기 V5", layout="wide")
st.title("🎬 신프로의 스마트 실사 수집 엔진 (V5 초고속 & 안정화)")

with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key = st.text_input("Pexels API Key", type="password")
    user_gemini_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    # 50개까지 슬라이더 전격 확장!
    video_count = st.slider("영상 개수", 1, 50, 20)
    image_count = st.slider("이미지 개수", 1, 50, 10)
    project_name = st.text_input("프로젝트명 (ZIP 파일명)", "ShinPro_Project")

script_input = st.text_area("📄 1만 자 대본을 마음껏 붙여넣으세요 (내부에서 알아서 분할 처리됩니다)", height=300)

def clean_filename(text):
    # 파일명에 쓸 수 없는 특수문자 제거
    return re.sub(r'[\\/*?:"<>|]', "", text)

# [업데이트 1] 1만 자 대본 에러 방지용 자동 분할 추출
def get_keywords_chunked(script, total_count, type_name, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # 대본을 2000자씩 분할
    chunk_size = 2000
    chunks = [script[i:i+chunk_size] for i in range(0, len(script), chunk_size)]
    
    # 50개를 요청했다면, 분할된 덩어리 개수에 맞춰 목표 개수를 배분
    base_count = total_count // len(chunks)
    remainder = total_count % len(chunks)
    counts = [base_count + 1 if i < remainder else base_count for i in range(len(chunks))]
    
    all_keys = []
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    for idx, (chunk, count) in enumerate(zip(chunks, counts)):
        if count == 0: continue
        progress_text.text(f"🧠 {type_name} 키워드 분석 중... ({idx+1}/{len(chunks)} 덩어리)")
        
        prompt = f"""
        다음 대본의 흐름을 파악하여 {type_name} 검색용 영어 키워드를 딱 {count}개만 시간 순서대로 뽑아줘. 
        출력 형식은 무조건 '영어키워드_한글요약' 형태로만 해. (예: sad crying_슬프게 우는 사람)
        대본: {chunk}
        """
        try:
            response = model.generate_content(prompt)
            lines = [k.strip() for k in response.text.split('\n') if k.strip() and '_' in k]
            all_keys.extend(lines)
        except Exception:
            pass # 에러가 나도 멈추지 않고 다음 덩어리로 넘어감
            
        progress_bar.progress((idx + 1) / len(chunks))
        
        # 무료 API 한도 초과 방지를 위한 15초 휴식 (마지막 덩어리가 아닐 때만)
        if idx < len(chunks) - 1:
            time.sleep(15) 
            
    return all_keys[:total_count]

# [업데이트 2] 단일 파일 다운로드 및 Vrew 최적화 이름 적용
def download_single_item(item, idx, asset_type, api_key, save_path):
    headers = {"Authorization": api_key}
    try:
        query = item.split('_')[0].strip() if '_' in item else item.strip()
        kor_meaning = item.split('_')[1].strip() if '_' in item else "키워드"
        
        base_url = "https://api.pexels.com/videos/search" if asset_type == "Videos" else "https://api.pexels.com/v1/search"
        url = f"{base_url}?query={query}&orientation=landscape&per_page=1"
        
        res = requests.get(url, headers=headers).json()
        items = res.get('videos') if asset_type == "Videos" else res.get('photos')
        
        if items:
            file_url = items[0]['video_files'][0]['link'] if asset_type == "Videos" else items[0]['src']['original']
            ext = "mp4" if asset_type == "Videos" else "jpg"
            
            # Vrew 최적화 파일명 설정 (001_영어_한글뜻.mp4)
            safe_name = clean_filename(f"{query}_{kor_meaning}".replace(" ", "_"))
            f_name = os.path.join(save_path, f"{idx+1:03d}_{safe_name}.{ext}")
            
            with open(f_name, 'wb') as f:
                f.write(requests.get(file_url, timeout=15).content)
            return True
    except Exception:
        return False
    return False

# [업데이트 3] 초고속 멀티스레드 엔진
def download_assets_fast(keywords, asset_type, api_key, folder_name):
    save_path = os.path.join(folder_name, asset_type)
    os.makedirs(save_path, exist_ok=True)
    
    success_count = 0
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    # 5개의 파이프라인으로 동시에 영상/사진을 빨아들임
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(download_single_item, item, idx, asset_type, api_key, save_path): item for idx, item in enumerate(keywords)}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            success = future.result()
            if success: success_count += 1
            completed += 1
            progress_text.text(f"⚡ {asset_type} 초고속 다운로드 중... ({completed}/{len(keywords)})")
            progress_bar.progress(completed / len(keywords))
            
    st.write(f"✅ {asset_type} {success_count}개 수집 완료!")

# 실행 메인 로직
if st.button("🚀 분석 및 초고속 다운로드 시작"):
    if not user_pexels_key or not user_gemini_key:
        st.error("API 키를 모두 입력해주세요.")
    elif not script_input:
        st.warning("대본을 입력해주세요.")
    else:
        # 기존 작업 폴더 초기화
        if os.path.exists(project_name): shutil.rmtree(project_name)
        os.makedirs(project_name)
        
        with st.spinner("V5 엔진 가동 중... (1만 자 대본은 중간중간 쉬어가며 처리하므로 여유를 가져주세요)"):
            try:
                # 1. 영상 작업
                if video_count > 0:
                    st.subheader("🎬 1단계: 영상 소스 작업")
                    v_keys = get_keywords_chunked(script_input, video_count, "영상", user_gemini_key)
                    download_assets_fast(v_keys, "Videos", user_pexels_key, project_name)
                
                # 2. 사진 작업
                if image_count > 0:
                    st.subheader("🖼️ 2단계: 이미지 소스 작업")
                    i_keys = get_keywords_chunked(script_input, image_count, "사진", user_gemini_key)
                    download_assets_fast(i_keys, "Images", user_pexels_key, project_name)
                
                # 3. ZIP 파일 생성 및 제공
                shutil.make_archive(project_name, 'zip', project_name)
                with open(f"{project_name}.zip", "rb") as f:
                    st.download_button(
                        label="📦 완성된 파일 다운로드 (ZIP)",
                        data=f,
                        file_name=f"{project_name}.zip",
                        mime="application/zip",
                        type="primary"
                    )
                st.success("🎉 모든 작업이 끝났습니다! 위 버튼을 눌러 압축파일을 다운로드하세요.")
            except Exception as e:
                st.error(f"최종 오류 발생: {e}")
