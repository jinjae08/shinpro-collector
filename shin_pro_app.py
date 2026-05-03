import streamlit as st
import requests
import os
import shutil
import csv
import io
import re
import time

st.set_page_config(page_title="신프로 CapCut 소스 공급기 v2.1", layout="wide")
st.title("🎬 신프로의 만능 소스 자동 수집기 v2.1")

# ── 사이드바 ────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 API 설정")
    user_pexels_key  = st.text_input("1. Pexels API Key",  type="password")
    user_pixabay_key = st.text_input("2. Pixabay API Key", type="password")
    st.divider()
    project_name   = st.text_input("프로젝트명", "ShinPro_Final")
    st.divider()

    st.markdown("**⏱ 요청 간격 설정**")
    req_interval = st.slider(
        "요청 간격 (초)",
        min_value=0.5, max_value=5.0, value=1.0, step=0.5,
        help="API 요청 간격. 느릴수록 안정적."
    )
    max_per_hour = int(3600 / req_interval)
    st.caption(f"현재 설정: {req_interval}초 간격 → 시간당 최대 {max_per_hour}회")
    st.divider()

    clear_existing = st.toggle("기존 파일 덮어쓰기", value=False)

    if st.button("🔍 API 키 테스트"):
        if user_pexels_key:
            try:
                r = requests.get(
                    "https://api.pexels.com/v1/search?query=nature&per_page=1",
                    headers={"Authorization": user_pexels_key}, timeout=10
                )
                if r.status_code == 200:
                    st.success("✅ Pexels API 정상")
                else:
                    st.error(f"❌ Pexels 오류: {r.status_code}")
            except Exception as e:
                st.error(f"❌ Pexels 연결 실패: {e}")
        if user_pixabay_key:
            try:
                r = requests.get(
                    f"https://pixabay.com/api/?key={user_pixabay_key}&q=nature&per_page=3",
                    timeout=10
                )
                if r.status_code == 200:
                    st.success("✅ Pixabay API 정상")
                else:
                    st.error(f"❌ Pixabay 오류: {r.status_code}")
            except Exception as e:
                st.error(f"❌ Pixabay 연결 실패: {e}")

    st.divider()
    if st.button("🗑 중복 ID 초기화"):
        if 'downloaded_ids' in st.session_state:
            st.session_state.downloaded_ids = set()
            st.success("초기화 완료")

# ── 메인 레이아웃: 2컬럼 ────────────────────────────────────
col_left, col_right = st.columns(2)

# ── 1단계: CSV 업로드 ────────────────────────────────────────
with col_left:
    st.markdown("### 📂 1단계: CSV 업로드")
    st.caption("Claude가 만든 CSV 파일 (v5.1 both 타입 지원)")
    uploaded_file = st.file_uploader(
        "파일을 드래그 앤 드롭 하세요",
        type=['csv', 'txt'],
        label_visibility="collapsed"
    )

# ── 2단계: 키워드 붙여넣기 ───────────────────────────────────
with col_right:
    st.markdown("### 🔑 2단계: 키워드 붙여넣기")
    st.caption("Claude 출력 키워드를 그대로 붙여넣으세요")

    tab_img, tab_vid = st.tabs(["📷 이미지 키워드", "🎬 영상 키워드"])

    with tab_img:
        img_keyword_raw = st.text_area(
            "이미지 키워드",
            placeholder="001 | airport control room supervisor alarm\n002 | europe oil pipeline night crisis\n...",
            height=200,
            label_visibility="collapsed"
        )

    with tab_vid:
        vid_keyword_raw = st.text_area(
            "영상 키워드",
            placeholder="001 | control room alarm warning lights\n002 | europe oil crisis pipeline aerial\n...",
            height=200,
            label_visibility="collapsed"
        )

st.divider()

# ── 키워드 파싱 함수 ─────────────────────────────────────────
def parse_keywords(raw_text: str) -> dict:
    """
    001 | keyword here
    002 | another keyword
    형식을 파싱해서 {1: "keyword here", 2: "another keyword"} 반환
    """
    result = {}
    if not raw_text.strip():
        return result
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d+)\s*\|\s*(.+)$', line)
        if m:
            num = int(m.group(1))
            kw  = m.group(2).strip()
            result[num] = kw
    return result

# ── CSV 파싱 함수 ─────────────────────────────────────────────
def parse_csv(uploaded) -> list:
    raw = uploaded.getvalue().decode('utf-8-sig')
    match = re.search(r'scene_number,.*', raw, re.DOTALL)
    if not match:
        return []
    return list(csv.DictReader(io.StringIO(match.group(0).strip())))

# ── 다운로드 함수 ─────────────────────────────────────────────
def download_asset(asset_type, file_number, keyword, p_key, pb_key, save_path, log_ph):
    if 'downloaded_ids' not in st.session_state:
        st.session_state.downloaded_ids = set()

    asset_id = f"{asset_type}_{int(file_number):03d}"

    f_ext  = 'mp4' if asset_type == 'video' else 'jpg'
    f_name = os.path.join(save_path, f"{int(file_number):03d}.{f_ext}")

    if os.path.exists(f_name) and not clear_existing:
        if asset_id not in st.session_state.downloaded_ids:
            log_ph.info(f"⏭ {asset_type} #{int(file_number):03d} 이미 존재 — 스킵")
            st.session_state.downloaded_ids.add(asset_id)
        return True

    file_url    = None
    source_used = ""
    q = requests.utils.quote(keyword)

    # ── Pexels ──────────────────────────────────────────────
    if p_key:
        headers = {"Authorization": p_key}
        try:
            if asset_type == 'video':
                res = requests.get(
                    f"https://api.pexels.com/videos/search?query={q}&orientation=landscape&per_page=15&size=medium",
                    headers=headers, timeout=15
                ).json()
                videos = res.get('videos', [])
                if videos:
                    pick = videos[int(file_number) % len(videos)]
                    for vf in pick.get('video_files', []):
                        if vf.get('file_type') == 'video/mp4' and vf.get('quality') in ('hd', 'sd'):
                            file_url = vf['link']
                            break
                    if not file_url and pick.get('video_files'):
                        file_url = pick['video_files'][0]['link']
                    source_used = "Pexels"
            else:
                res = requests.get(
                    f"https://api.pexels.com/v1/search?query={q}&orientation=landscape&per_page=15&size=medium",
                    headers=headers, timeout=15
                ).json()
                photos = res.get('photos', [])
                if photos:
                    pick = photos[int(file_number) % len(photos)]
                    file_url = pick['src'].get('large', pick['src'].get('medium'))
                    source_used = "Pexels"
        except Exception as e:
            log_ph.warning(f"Pexels 오류 #{file_number}: {e}")

    # ── Pixabay 폴백 ─────────────────────────────────────────
    if not file_url and pb_key:
        try:
            if asset_type == 'video':
                res = requests.get(
                    f"https://pixabay.com/api/videos/?key={pb_key}&q={q}&orientation=horizontal&per_page=15",
                    timeout=15
                ).json()
                hits = res.get('hits', [])
                if hits:
                    pick = hits[int(file_number) % len(hits)]
                    file_url = pick.get('videos', {}).get('medium', {}).get('url')
                    source_used = "Pixabay"
            else:
                res = requests.get(
                    f"https://pixabay.com/api/?key={pb_key}&q={q}&image_type=photo&orientation=horizontal&per_page=15",
                    timeout=15
                ).json()
                hits = res.get('hits', [])
                if hits:
                    pick = hits[int(file_number) % len(hits)]
                    file_url = pick.get('largeImageURL')
                    source_used = "Pixabay"
        except Exception as e:
            log_ph.warning(f"Pixabay 오류 #{file_number}: {e}")

    # ── 실제 다운로드 ────────────────────────────────────────
    if file_url:
        try:
            r = requests.get(file_url, stream=True, timeout=60)
            r.raise_for_status()
            with open(f_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            log_ph.success(f"✅ [{source_used}] {asset_type} #{int(file_number):03d} → {keyword[:45]}")
            st.session_state.downloaded_ids.add(asset_id)
            return True
        except Exception as e:
            log_ph.error(f"❌ 저장 실패 {asset_type} #{file_number}: {e}")
    else:
        log_ph.error(f"❌ URL 없음 — {asset_type} #{file_number} | 키워드: {keyword}")

    return False

# ── 수집 가동 버튼 ───────────────────────────────────────────
if st.button("🚀 즉시 수집 가동", type="primary", use_container_width=True):

    # 유효성 검사
    if not user_pexels_key and not user_pixabay_key:
        st.error("Pexels 또는 Pixabay API Key를 입력해주세요.")
        st.stop()
    if not uploaded_file:
        st.error("CSV 파일을 업로드해주세요.")
        st.stop()
    if not img_keyword_raw.strip() and not vid_keyword_raw.strip():
        st.error("이미지 또는 영상 키워드를 입력해주세요.")
        st.stop()

    # 파싱
    img_kw = parse_keywords(img_keyword_raw)
    vid_kw = parse_keywords(vid_keyword_raw)
    rows   = parse_csv(uploaded_file)

    if not rows:
        st.error("CSV에서 유효한 데이터를 찾을 수 없습니다.")
        st.stop()

    st.success(f"✅ CSV {len(rows)}개 씬 감지 | 이미지 키워드 {len(img_kw)}개 | 영상 키워드 {len(vid_kw)}개")

    # 폴더 세팅
    v_path = f"{project_name}/Videos"
    i_path = f"{project_name}/Images"
    if clear_existing:
        shutil.rmtree(v_path, ignore_errors=True)
        shutil.rmtree(i_path, ignore_errors=True)
    os.makedirs(v_path, exist_ok=True)
    os.makedirs(i_path, exist_ok=True)

    # CSV에서 번호 추출
    img_nums = []
    vid_nums = []
    for row in rows:
        i_num = row.get('image_number', '').strip()
        v_num = row.get('video_number', '').strip()
        if i_num and i_num.isdigit():
            n = int(i_num)
            if n not in img_nums: img_nums.append(n)
        if v_num and v_num.isdigit():
            n = int(v_num)
            if n not in vid_nums: vid_nums.append(n)

    total    = len(img_nums) + len(vid_nums)
    progress = st.progress(0)
    log_area = st.empty()
    done     = 0
    s_img = f_img = s_vid = f_vid = 0

    # 이미지 수집
    for n in sorted(img_nums):
        kw = img_kw.get(n, f"cinematic scene {n}")
        ok = download_asset('image', n, kw, user_pexels_key, user_pixabay_key, i_path, log_area)
        if ok: s_img += 1
        else:  f_img += 1
        done += 1
        progress.progress(done / total)
        time.sleep(req_interval)

    # 영상 수집
    for n in sorted(vid_nums):
        kw = vid_kw.get(n, f"cinematic video {n}")
        ok = download_asset('video', n, kw, user_pexels_key, user_pixabay_key, v_path, log_area)
        if ok: s_vid += 1
        else:  f_vid += 1
        done += 1
        progress.progress(done / total)
        time.sleep(req_interval)

    # 결과 요약
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("이미지 성공", f"{s_img}장")
    c2.metric("이미지 실패", f"{f_img}장")
    c3.metric("영상 성공",   f"{s_vid}개")
    c4.metric("영상 실패",   f"{f_vid}개")

    # ZIP 다운로드
    shutil.make_archive(project_name, 'zip', project_name)
    st.success("🎉 수집 완료! 아래 버튼으로 전체 패키지를 다운로드하세요.")
    with open(f"{project_name}.zip", "rb") as f:
        st.download_button(
            "📦 전체 패키지 다운로드",
            f,
            file_name=f"{project_name}.zip",
            mime="application/zip"
        )
