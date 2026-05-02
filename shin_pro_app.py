import streamlit as st
import requests
import os
import shutil
import re
import time
from pathlib import Path
from google import genai

# ──────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────
st.set_page_config(page_title="신프로 캡컷 소스 공급기 v2", layout="wide")
st.title("🎬 신프로의 CapCut 소스 공급기 v2.0 (Pexels + Pixabay 듀얼엔진)")

# ──────────────────────────────────────────────
# 사이드바 설정
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key  = st.text_input("Pexels API Key",   type="password")
    user_pixabay_key = st.text_input("Pixabay API Key",  type="password")
    user_gemini_key  = st.text_input("Gemini API Key (A플랜 전용)", type="password")
    st.divider()

    # ✅ 로컬 저장 경로 직접 지정 (서버 RAM 폭발 방지 핵심!)
    default_path = str(Path.home() / "Desktop" / "CapCut_Sources")
    save_root = st.text_input("💾 로컬 저장 경로", value=default_path)
    project_name = st.text_input("📁 프로젝트 폴더명", "ShinPro_Project_01")

    st.divider()
    st.header("⚙️ 다운로드 품질 설정")
    video_quality = st.selectbox(
        "영상 화질 (16:9 롱폼 기준)",
        ["large (3840x2160 / 4K)", "medium (1920x1080 / FHD)", "small (1280x720 / HD)"],
        index=1  # 기본값: FHD
    )
    quality_key = video_quality.split(" ")[0]  # "large" / "medium" / "small"

    st.divider()
    st.caption("📌 로컬 실행 전용 버전 — 파일은 ZIP 없이 폴더에 직접 저장됩니다.")

# ──────────────────────────────────────────────
# 플랜 선택
# ──────────────────────────────────────────────
st.markdown("### ⚙️ 작업 방식 선택")
mode = st.radio(
    "Gemini API 에러 시 B플랜을 선택하세요.",
    ["A플랜: 대본 넣고 자동 추출 (Gemini API)", "B플랜: 키워드 직접 입력 (즉시 다운로드)"]
)

if "A플랜" in mode:
    script_input = st.text_area("📄 대본을 여기에 입력하세요", height=200)
    col1, col2 = st.columns(2)
    with col1: video_count = st.slider("영상 개수", 1, 50, 20)
    with col2: image_count = st.slider("이미지 개수", 1, 50, 10)
else:
    st.info("💡 ChatGPT 또는 Gemini에서 키워드를 뽑아 아래에 붙여넣으세요 (한 줄 = 하나)")
    manual_video_keys = st.text_area("🎥 영상 키워드 (영어키워드_한글의미 또는 영어만)", height=150)
    manual_image_keys = st.text_area("🖼️ 이미지 키워드 (영어키워드_한글의미 또는 영어만)", height=100)


# ──────────────────────────────────────────────
# Gemini 키워드 추출
# ──────────────────────────────────────────────
def extract_keywords_with_genai(script, count, type_name, api_key):
    client = genai.Client(api_key=api_key)
    prompt = (
        f"다음 대본을 읽고 {type_name} 검색용 영어 키워드 {count}개를 "
        f"'영어키워드_한글의미' 형태로만 추출해. "
        f"번호나 다른 설명은 절대 금지. 한 줄에 하나씩만.\n대본: {script}"
    )
    response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
    raw_lines = response.text.split('\n')
    result = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        # 앞 번호 제거 (예: "1. keyword_한글" → "keyword_한글")
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
        if '_' in line or line.isascii():
            result.append(line)
    return result


# ──────────────────────────────────────────────
# 핵심 함수: 스트리밍 다운로드 (RAM 폭발 방지)
# ──────────────────────────────────────────────
def stream_download(url, file_path, headers=None):
    """파일을 RAM에 올리지 않고 청크 단위로 직접 디스크에 저장"""
    try:
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):  # 512KB 청크
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        return False


# ──────────────────────────────────────────────
# Pexels 다운로드 함수
# ──────────────────────────────────────────────
def fetch_from_pexels(query, asset_type, api_key, save_path, file_prefix):
    headers = {"Authorization": api_key}
    if asset_type == "Videos":
        url = f"https://api.pexels.com/videos/search?query={query}&orientation=landscape&per_page=3"
        res = requests.get(url, headers=headers, timeout=10).json()
        items = res.get('videos', [])
        if not items:
            return False, "결과 없음"
        
        # 화질 기준 정렬 (width 기준 내림차순)
        video = items[0]
        video_files = video.get('video_files', [])
        best = max(video_files, key=lambda x: x.get('width', 0))
        file_url = best['link']
        ext = "mp4"
    else:
        url = f"https://api.pexels.com/v1/search?query={query}&orientation=landscape&per_page=3"
        res = requests.get(url, headers=headers, timeout=10).json()
        items = res.get('photos', [])
        if not items:
            return False, "결과 없음"
        file_url = items[0]['src']['large2x']  # 고해상도 이미지
        ext = "jpg"

    f_name = os.path.join(save_path, f"{file_prefix}.{ext}")
    success = stream_download(file_url, f_name)
    return success, f_name if success else "다운로드 실패"


# ──────────────────────────────────────────────
# Pixabay 폴백 다운로드 함수
# ──────────────────────────────────────────────
def fetch_from_pixabay(query, asset_type, api_key, save_path, file_prefix, quality_key="medium"):
    if asset_type == "Videos":
        url = (
            f"https://pixabay.com/api/videos/"
            f"?key={api_key}&q={requests.utils.quote(query)}"
            f"&video_type=film&per_page=3&safesearch=true"
        )
        res = requests.get(url, timeout=10).json()
        items = res.get('hits', [])
        if not items:
            return False, "결과 없음"
        
        # large → medium → small 순서로 폴백
        videos_obj = items[0].get('videos', {})
        for q in [quality_key, "medium", "small"]:
            candidate = videos_obj.get(q, {})
            file_url = candidate.get('url', '')
            if file_url:
                break
        if not file_url:
            return False, "URL 없음"
        ext = "mp4"
    else:
        url = (
            f"https://pixabay.com/api/"
            f"?key={api_key}&q={requests.utils.quote(query)}"
            f"&image_type=photo&orientation=horizontal"
            f"&min_width=1280&per_page=3&safesearch=true"
        )
        res = requests.get(url, timeout=10).json()
        items = res.get('hits', [])
        if not items:
            return False, "결과 없음"
        file_url = items[0].get('largeImageURL', '')
        if not file_url:
            return False, "URL 없음"
        ext = "jpg"

    f_name = os.path.join(save_path, f"{file_prefix}_pixabay.{ext}")
    success = stream_download(file_url, f_name)
    return success, f_name if success else "다운로드 실패"


# ──────────────────────────────────────────────
# 통합 다운로드 오케스트레이터
# ──────────────────────────────────────────────
def download_assets(keywords, asset_type, pexels_key, pixabay_key, folder_path, quality_key):
    sub_folder = "영상" if asset_type == "Videos" else "이미지"
    save_path = os.path.join(folder_path, sub_folder)
    os.makedirs(save_path, exist_ok=True)

    total = len(keywords)
    progress_bar = st.progress(0)
    status_box   = st.empty()
    result_log   = []

    for idx, item in enumerate(keywords):
        if not item.strip():
            continue

        # 키워드 파싱
        query     = item.split('_')[0].strip() if '_' in item else item.strip()
        query     = re.sub(r'[^\w\s]', '', query)  # 특수문자 제거
        safe_name = re.sub(r'[\\/*?:"<>|]', "", item.replace(' ', '_'))
        prefix    = f"{idx+1:03d}_{safe_name}"

        status_box.info(f"🔄 [{idx+1}/{total}] '{query}' 수집 중... (Pexels 시도)")

        # 1차: Pexels
        success, result = fetch_from_pexels(query, asset_type, pexels_key, save_path, prefix)

        # 2차: Pixabay 폴백
        if not success and pixabay_key:
            status_box.warning(f"⚡ [{idx+1}/{total}] Pexels 실패 → Pixabay로 폴백 중...")
            success, result = fetch_from_pixabay(query, asset_type, pixabay_key, save_path, prefix, quality_key)

        # 결과 로그
        if success:
            result_log.append(f"✅ [{idx+1:03d}] {item}")
        else:
            result_log.append(f"❌ [{idx+1:03d}] {item} — 양쪽 모두 실패")

        # 진행률 업데이트
        progress_bar.progress((idx + 1) / total)

        # Rate Limit 방지: 0.4초 딜레이
        time.sleep(0.4)

    status_box.empty()
    return result_log


# ──────────────────────────────────────────────
# 실행 버튼
# ──────────────────────────────────────────────
if st.button("🚀 캡컷 소스 다운로드 시작", type="primary"):

    # 유효성 검사
    if not user_pexels_key and not user_pixabay_key:
        st.error("❌ Pexels 또는 Pixabay API Key 중 하나는 반드시 입력해야 합니다.")
        st.stop()

    # 저장 경로 준비
    project_path = os.path.join(save_root, project_name)
    os.makedirs(project_path, exist_ok=True)

    try:
        # 키워드 준비
        if "A플랜" in mode:
            if not user_gemini_key or not script_input:
                st.error("❌ Gemini API Key와 대본을 모두 입력해주세요.")
                st.stop()
            with st.spinner("🤖 Gemini가 키워드를 추출하고 있습니다..."):
                v_keys = extract_keywords_with_genai(script_input, video_count, "영상", user_gemini_key)
                i_keys = extract_keywords_with_genai(script_input, image_count, "사진", user_gemini_key)
            st.success(f"✅ 키워드 추출 완료 — 영상 {len(v_keys)}개 / 이미지 {len(i_keys)}개")
            with st.expander("📋 추출된 키워드 확인"):
                st.write("**영상 키워드:**", v_keys)
                st.write("**이미지 키워드:**", i_keys)
        else:
            v_keys = [k for k in manual_video_keys.split('\n') if k.strip()]
            i_keys = [k for k in manual_image_keys.split('\n') if k.strip()]

        # ── 영상 다운로드 ──
        if v_keys:
            st.markdown("#### 🎬 영상 수집 중...")
            v_log = download_assets(v_keys, "Videos", user_pexels_key, user_pixabay_key, project_path, quality_key)
            with st.expander(f"📄 영상 수집 결과 ({len(v_keys)}개)"):
                for line in v_log:
                    st.write(line)

        # ── 이미지 다운로드 ──
        if i_keys:
            st.markdown("#### 🖼️ 이미지 수집 중...")
            i_log = download_assets(i_keys, "Images", user_pexels_key, user_pixabay_key, project_path, quality_key)
            with st.expander(f"📄 이미지 수집 결과 ({len(i_keys)}개)"):
                for line in i_log:
                    st.write(line)

        # ── 완료 메시지 ──
        st.balloons()
        st.success(f"""
        🎉 **모든 소스 수집 완료!**

        📂 저장 위치: `{project_path}`
        └── 📁 영상/  (mp4 파일들)
        └── 📁 이미지/ (jpg 파일들)

        👆 위 경로를 탐색기에서 열어 캡컷에 드래그하세요!
        """)

        # 폴더 바로 열기 버튼 (Windows 전용)
        if st.button("📂 저장 폴더 열기 (Windows)"):
            os.startfile(project_path)

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        st.exception(e)
