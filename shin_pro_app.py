import streamlit as st
import requests
import os
import time
import zipfile
import io
import google.generativeai as genai

st.set_page_config(page_title="신프로 실사 수집기", layout="wide")
st.title("🎬 신프로의 스마트 실사 수집기")

with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key = st.text_input("Pexels API Key", type="password")
    user_gemini_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    video_count = st.slider("영상 개수", 1, 20, 3)
    image_count = st.slider("이미지 개수", 1, 20, 2)
    project_name = st.text_input("프로젝트명 (ZIP 파일명)", "ShinPro_Project")

script_input = st.text_area("📄 대본을 여기에 입력하세요", height=300)

def get_keywords_chunked(script, count, type_name, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    chunk_size = 2000
    chunks = [script[i:i+chunk_size] for i in range(0, len(script), chunk_size)]
    all_keys = []
    st.info(f"총 {len(chunks)}개 덩어리 분석 시작")
    for i, chunk in enumerate(chunks):
        st.write(f"⚙️ 분석 중... ({i+1}/{len(chunks)})")
        prompt = f"다음 대본에서 Pexels {type_name} 검색용 영어 키워드를 {count}개 뽑아줘. 반드시 '영어키워드_한글요약' 형식으로만 한 줄씩 출력해. 다른 설명 절대 없이.\n대본: {chunk}"
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                lines = [k.strip() for k in response.text.split('\n') if k.strip() and '_' in k]
                all_keys.extend(lines)
                st.write(f"  → {len(lines)}개 키워드 추출 ✅")
                if i < len(chunks) - 1:
                    st.info("⏳ API 한도 보호 중... 15초 대기")
                    time.sleep(15)
                break
            except Exception as e:
                st.warning(f"⚠️ 재시도 {attempt+1}/3 - {e}")
                time.sleep(30)
    return all_keys[:count]

def fetch_assets(keywords, asset_type, api_key):
    """파일을 서버에 저장하지 않고 메모리에 담아서 반환"""
    headers = {"Authorization": api_key}
    files = {}  # {파일명: 바이트데이터}
    for idx, item in enumerate(keywords):
        query = item.split('_')[0] if '_' in item else item
        if asset_type == "Videos":
            url = f"https://api.pexels.com/videos/search?query={query}&orientation=landscape&per_page=3"
        else:
            url = f"https://api.pexels.com/v1/search?query={query}&orientation=landscape&per_page=3"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            data = res.json()
            if asset_type == "Videos":
                items = data.get('videos', [])
                if not items:
                    st.warning(f"⚠️ [{idx+1:03d}] '{query}' 결과 없음")
                    continue
                video_files = items[0].get('video_files', [])
                hd = [v for v in video_files if v.get('quality') in ['hd', 'sd']]
                file_url = hd[0]['link'] if hd else video_files[0]['link']
                ext = "mp4"
            else:
                items = data.get('photos', [])
                if not items:
                    st.warning(f"⚠️ [{idx+1:03d}] '{query}' 결과 없음")
                    continue
                file_url = items[0]['src']['large2x']
                ext = "jpg"
            safe = item.replace(' ', '_').replace('/', '_').replace(':', '').replace('*', '')[:50]
            fname = f"{asset_type}/{idx+1:03d}_{safe}.{ext}"
            r = requests.get(file_url, timeout=30, stream=True)
            r.raise_for_status()
            files[fname] = r.content
            st.write(f"✅ [{idx+1:03d}] {item}")
        except requests.exceptions.Timeout:
            st.error(f"❌ [{idx+1:03d}] 타임아웃 - '{query}'")
        except Exception as e:
            st.error(f"❌ [{idx+1:03d}] 오류: {e}")
    return files

if st.button("🚀 시작"):
    if not user_pexels_key or not user_gemini_key:
        st.error("❌ API 키를 입력하세요.")
    elif not script_input.strip():
        st.error("❌ 대본을 입력하세요.")
    else:
        all_files = {}

        # 영상 처리
        st.subheader("📹 영상 처리 중...")
        v_keys = get_keywords_chunked(script_input, video_count, "영상", user_gemini_key)
        st.success(f"✅ 영상 키워드 {len(v_keys)}개 추출 완료!")
        v_files = fetch_assets(v_keys, "Videos", user_pexels_key)
        all_files.update(v_files)

        # 60초 대기
        st.info("⏳ API 한도 보호를 위해 60초 대기 중... 잠깐만요!")
        time.sleep(60)

        # 이미지 처리
        st.subheader("🖼️ 이미지 처리 중...")
        i_keys = get_keywords_chunked(script_input, image_count, "이미지", user_gemini_key)
        st.success(f"✅ 이미지 키워드 {len(i_keys)}개 추출 완료!")
        i_files = fetch_assets(i_keys, "Images", user_pexels_key)
        all_files.update(i_files)

        # ZIP으로 묶기
        st.info("📦 ZIP 파일로 묶는 중...")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname, fdata in all_files.items():
                zf.writestr(f"{project_name}/{fname}", fdata)
        zip_buffer.seek(0)

        st.balloons()
        st.success(f"🎉 완료! 영상 {len(v_files)}개 + 이미지 {len(i_files)}개")

        # 다운로드 버튼
        st.download_button(
            label="📥 ZIP 다운로드 (클릭!)",
            data=zip_buffer,
            file_name=f"{project_name}.zip",
            mime="application/zip"
        )
