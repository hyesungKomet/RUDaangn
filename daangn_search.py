# streamlit_app.py
import os
import streamlit as st
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# 페이지 레이아웃
st.set_page_config(layout="wide")
st.title("ARE YOU DAANGN?")

# SSL 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 세션 상태 초기화 ---
if "is_searching" not in st.session_state:
    st.session_state.is_searching = False
if "stop_search" not in st.session_state:
    st.session_state.stop_search = False
if "results_df" not in st.session_state:
    st.session_state.results_df = pd.DataFrame()

# --- 1) 지역 코드 CSV 로드 ---
@st.cache_data
def load_regions():
    df = pd.read_csv("address_with_all_codes.csv", dtype=str)
    df = df.drop_duplicates(subset=["검색어", "region_name", "region_code"]).copy()
    # 광역 컬럼 생성 (검색어의 첫 번째 단어)
    df["광역"] = df["검색어"].map(lambda x: x.split()[0])
    MAJORS = [
        "서울특별시","부산광역시","대구광역시","인천광역시","광주광역시",
        "대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도",
        "충청북도","충청남도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"
    ]
    return df, MAJORS

regions_df, MAJORS = load_regions()

# --- 2) 검색 파라미터 UI ---
row1_col1, row1_col2, row1_col3 = st.columns([1, 1, 4])
with row1_col1:
    mode = st.radio("🔎 모드", ["전국 검색", "지역 검색"], index=1, horizontal=True)
with row1_col2:
    # --- UI: 병렬 검색 옵션 추가 ---
    parallel = st.checkbox(
        "빠른 검색 사용",
        value=False,
        help="아직 실험중..."
    )
with row1_col3:
    item = st.text_input("찾을 물품 (ex: 노트북)", "")

row2_cols = st.columns([3, 2, 1, 1, 1])
with row2_cols[0]:
    kws = st.text_input(
        "핵심 키워드 - 쉼표로 구분 (ex: 게이밍, 3060)",
        help="제목+내용에 모두 포함된 항목만 필터링"
    )
    keywords = [w.strip().lower() for w in kws.split(",") if w.strip()]
with row2_cols[1]:
    period = st.selectbox(
        "등록 기간",
        ["전체","1일","7일","1개월","3개월","6개월","1년"],
        help="기간별 최근 등록글만 검색"
    )
with row2_cols[2]:
    only_available = st.checkbox(
        "판매중만 보기", value=False,
        help="판매완료된 글 제외"
    )
with row2_cols[3]:
    min_price = st.number_input(
        "최소 가격", value=0, step=1000,
        help="원 단위로 최소 가격 설정"
    )
with row2_cols[4]:
    max_price = st.number_input(
        "최대 가격", value=0, step=1000,
        help="0이면 제한 없음"
    )

# 컷오프 계산 함수 (dateutil.relativedelta 사용)
def compute_cutoff(period):
    now = pd.Timestamp.now(tz="Asia/Seoul")
    if period == "1일": return now - relativedelta(days=1)
    if period == "7일": return now - relativedelta(days=7)
    if period == "1개월": return now - relativedelta(months=1)
    if period == "3개월": return now - relativedelta(months=3)
    if period == "6개월": return now - relativedelta(months=6)
    if period == "1년": return now - relativedelta(years=1)
    return None

cutoff = compute_cutoff(period)

# --- 3) 지역 검색 필터 ---
sub_sel = []
if mode == "지역 검색":
    with st.expander("지역 필터 설정", expanded=True):
        maj_sel = st.multiselect("광역 선택", MAJORS, default=MAJORS[:3])
        sub_df = regions_df[regions_df["광역"].isin(maj_sel)]
        sub_opts = sorted(sub_df["검색어"].unique())
        sub_sel = st.multiselect("동/읍/면 선택 (비워두면 모두)", sub_opts)
        if not sub_sel:
            sub_sel = sub_opts.copy()

# --- 4) 페이지네이션 ---
pag1, pag2 = st.columns(2)
with pag1:
    per_page = st.number_input(
        "페이지당 항목 수",
        1, 100, 10, 1,
        help="limit: 한 페이지당 불러올 게시물 수. 내부 API의 limit 파라미터"
    )
with pag2:
    page = st.number_input(
        "페이지 번호",
        1, 100, 1, 1,
        help="page: 불러올 페이지 번호. 1부터 시작"
    )

# --- 5) 내부 API 호출 함수 ---
@st.cache_data
def fetch_articles(region_tag, query, page, limit):
    """
    region_tag: "동이름-코드" 형태
    query: 검색어
    page: 페이지 번호
    limit: 한 페이지당 아이템 수
    내부 API는 page와 limit을 이용해 페이징된 결과를 반환합니다.
    전체를 가져오려면 page를 순차적으로 증가시켜 호출해야 합니다.
    """
    url = "https://www.daangn.com/kr/buy-sell/"
    params = {
        "in": region_tag,
        "search": query,
        "_data": "routes/kr.buy-sell._index",
        "page": page,
        "limit": limit
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.daangn.com/kr/buy-sell/",
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(url, params=params, headers=headers, verify=False)
    r.raise_for_status()
    return r.json()

# --- 6) 검색/중지 제어 버튼 ---
with st.form('search form'):
    col_start, col_stop = st.columns([1,1])
    with col_start:
        start = st.form_submit_button("🔎 검색 시작")
    with col_stop:
        stop = st.form_submit_button("🛑 검색 중지")

    # 사용자가 start 누르면 is_searching 켜고, stop 누르면 끄기
    if start:
        st.session_state.is_searching = True
        st.session_state.stop_search = False
    if stop:
        st.session_state.stop_search = True

# --- 7) 검색 실행 & 점진적 렌더링 ---
if st.session_state.is_searching:
    # 항상 빈 df_mid 정의
    df_mid = pd.DataFrame()
    
    # 대상 지역 리스트 구성
    if mode == "전국 검색":
        regions_to_search = (
            regions_df[["검색어","region_name","region_code"]]
            .drop_duplicates()
            .values.tolist()
        )
    else:
        sub_df = regions_df[regions_df["검색어"].isin(sub_sel)]
        regions_to_search = (
            sub_df[["검색어","region_name","region_code"]]
            .drop_duplicates()
            .values.tolist()
        )

    all_rows = []
    progress = st.progress(0)
    result_container = st.empty()
    # is_cloud = "STREAMLIT_APP_NAME" in os.environ
    total = len(regions_to_search)

    if parallel:
        # 로컬: 병렬 처리
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {
                executor.submit(
                    fetch_articles,
                    f"{rname}-{rcode}", item, page, per_page
                ): (full, rname)
                for full, rname, rcode in regions_to_search
            }
            done = 0
            for future in as_completed(future_map):
                if st.session_state.stop_search:
                    break
                full, rname = future_map[future]
                data = future.result()
                arts = data.get("allPage", {}).get("fleamarketArticles", [])
                for art in arts:
                    created = pd.to_datetime(art["createdAt"])
                    if cutoff and created < cutoff:
                        continue
                    txt = (art["title"] + " " + art["content"]).lower()
                    if keywords and not all(kw in txt for kw in keywords):
                        continue
                    try:
                        price = int(float(art["price"]))
                    except:
                        price = None
                    sold = art.get("status", "").lower() == "closed"
                    if only_available and sold:
                        continue
                    if max_price > 0 and price is not None and price > max_price:
                        continue
                    if price is not None and price < min_price:
                        continue
                    all_rows.append({
                        "주소": full,
                        "동/읍/면": rname,
                        "제목": art["title"],
                        "가격": price,
                        "등록시간": created,
                        "판매자": art["user"]["nickname"],
                        "판매완료": "예" if sold else "아니오",
                        "링크": art["href"],
                        "썸네일": art.get("thumbnail")
                    })
                done += 1
                progress.progress(done / total)
                df_mid = (
                    pd.DataFrame(all_rows)
                    .drop_duplicates(subset=["링크"])  
                    .reset_index(drop=True)
                )
                result_container.dataframe(df_mid, use_container_width=True)
    else:
        # 서버(Cloud): 순차 처리
        for idx, (full, rname, rcode) in enumerate(regions_to_search):
            if st.session_state.stop_search:
                break
            data = fetch_articles(f"{rname}-{rcode}", item, page, per_page)
            arts = data.get("allPage", {}).get("fleamarketArticles", [])
            for art in arts:
                created = pd.to_datetime(art["createdAt"])
                if cutoff and created < cutoff:
                    continue
                txt = (art["title"] + " " + art["content"]).lower()
                if keywords and not all(kw in txt for kw in keywords):
                    continue
                try:
                    price = int(float(art["price"]))
                except:
                    price = None
                sold = art.get("status", "").lower() == "closed"
                if only_available and sold:
                    continue
                if max_price > 0 and price is not None and price > max_price:
                    continue
                if price is not None and price < min_price:
                    continue
                all_rows.append({
                    "주소": full,
                    "동/읍/면": rname,
                    "제목": art["title"],
                    "가격": price,
                    "등록시간": created,
                    "판매자": art["user"]["nickname"],
                    "판매완료": "예" if sold else "아니오",
                    "링크": art["href"],
                    "썸네일": art.get("thumbnail")
                })
            progress.progress((idx + 1) / total)
            df_mid = (
                pd.DataFrame(all_rows)
                .drop_duplicates(subset=["링크"])  
                .reset_index(drop=True)
            )
            result_container.dataframe(df_mid, use_container_width=True)

    st.session_state.is_searching = False
    st.session_state.results_df = df_mid

# --- 8) 결과 출력 & 다운로드 ---
df_final = st.session_state.results_df
if not df_final.empty:
    st.success(f"✅ 총 {len(df_final)}건 검색 완료")
    csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("📥 결과 다운로드", data=csv, file_name="results.csv", mime="text/csv")
    if mode == "지역 검색":
        st.markdown("### 카드 뷰")
        recs = df_final.to_dict('records')
        for i in range(0, len(recs), 3):
            cols = st.columns(3, gap="small")
            for j, rec in enumerate(recs[i:i+3]):
                with cols[j]:
                    thumb = rec.get("썸네일")
                    if thumb:
                        st.image(thumb, use_container_width=True)
                    st.markdown(f"**{rec['제목']}**")
                    st.markdown(f"- 💰 {rec['가격']}원")
                    st.markdown(f"- 📍 {rec['동/읍/면']} | {rec['주소']}")
                    st.markdown(f"- 🕒 {rec['등록시간'].strftime('%Y-%m-%d %H:%M')}")
                    st.markdown(f"- 👤 {rec['판매자']} | 판매완료: {rec['판매완료']}")
                    st.markdown(f"[🔗 상세보기]({rec['링크']})")
                    st.markdown("---")
