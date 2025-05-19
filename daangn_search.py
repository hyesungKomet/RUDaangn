# streamlit_app.py
import streamlit as st
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
import urllib3

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
    df["광역"] = df["검색어"].map(lambda x: x.split()[0])
    MAJORS = [
        "서울특별시","부산광역시","대구광역시","인천광역시","광주광역시",
        "대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도",
        "충청북도","충청남도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"
    ]
    return df, MAJORS

regions_df, MAJORS = load_regions()

# --- 2) 검색 모드, 입력, 키워드, 등록기간, 판매상태 UI ---
mode_col, item_col, key_col, period_col, sale_col = st.columns([1,4,3,2,1])
with mode_col:
    mode = st.radio("🔎 모드", ["전국 검색", "지역 검색"], index=1, horizontal=True)
with item_col:
    item = st.text_input("찾을 물품 (ex: 노트북)", "")
with key_col:
    kws = st.text_input(
        "핵심 키워드 - 쉼표로 구분 (ex: 게이밍, 3060)",
        help="제목+내용에 모두 포함된 항목만 필터링"
    )
    keywords = [w.strip().lower() for w in kws.split(",") if w.strip()]
with period_col:
    period = st.selectbox(
        "등록 기간",
        ["전체", "1일", "7일", "1개월", "3개월", "6개월", "1년"],
        help="기간별로 최근 등록글만 검색합니다"
    )
with sale_col:
    only_available = st.checkbox("판매중만 보기", value=False, help="판매완료된 글을 제외합니다.")

# 기간 컷오프 계산
now = pd.Timestamp.now(tz="Asia/Seoul")
if period == "1일": cutoff = now - relativedelta(days=1)
elif period == "7일": cutoff = now - relativedelta(days=7)
elif period == "1개월": cutoff = now - relativedelta(months=1)
elif period == "3개월": cutoff = now - relativedelta(months=3)
elif period == "6개월": cutoff = now - relativedelta(months=6)
elif period == "1년": cutoff = now - relativedelta(years=1)
else: cutoff = None

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
    per_page = st.number_input("페이지당 항목 수", 5, 50, 10, 5)
with pag2:
    page = st.number_input("페이지 번호", 1, 100, 1, 1)

# --- 5) 내부 API 호출 함수 (SSL 검증 비활성화) ---
@st.cache_data
def fetch_articles(region_tag, query, page, limit):
    url = "https://www.daangn.com/kr/buy-sell/"
    params = {"in": region_tag, "search": query,
              "_data": "routes/kr.buy-sell._index",
              "page": page, "limit": limit}
    headers = {"Accept": "application/json, text/plain, */*",
               "Referer": "https://www.daangn.com/kr/buy-sell/",
               "User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API 요청 실패: {e}")
        return {}

# --- 6) 제어 버튼 ---
col_start, col_stop = st.columns([1,1])
with col_start:
    if st.button("🔎 검색 시작"):
        st.session_state.is_searching = True
        st.session_state.stop_search = False
with col_stop:
    if st.button("🛑 검색 중지"):
        st.session_state.stop_search = True

# --- 7) 검색 실행 & 점진적 렌더링 ---
if st.session_state.is_searching:
    df_mid = pd.DataFrame()
    if mode == "전국 검색":
        regions_to_search = (
            regions_df[["검색어","region_name","region_code"]]
            .drop_duplicates().values.tolist())
    else:
        sub_df = regions_df[regions_df["검색어"].isin(sub_sel)]
        regions_to_search = (
            sub_df[["검색어","region_name","region_code"]]
            .drop_duplicates().values.tolist())

    total = len(regions_to_search)
    progress = st.progress(0)
    result_container = st.empty()
    all_rows = []

    for idx, (full, rname, rcode) in enumerate(regions_to_search):
        if st.session_state.stop_search:
            st.warning("🛑 검색이 중지되었습니다.")
            break

        tag = f"{rname}-{rcode}"
        data = fetch_articles(tag, item, page, per_page)
        arts = data.get("allPage", {}).get("fleamarketArticles", [])

        for art in arts:
            created = pd.to_datetime(art["createdAt"])
            if cutoff and created < cutoff:
                continue
            txt = (art["title"] + " " + art["content"]).lower()
            if keywords and not all(kw in txt for kw in keywords):
                continue
            try:
                price_int = int(float(art["price"]))
            except:
                price_int = None
            sold = (art.get("status","" ) .lower() == "closed")
            if only_available and sold:
                continue

            all_rows.append({
                "주소": full,
                "동/읍/면": rname,
                "코드": rcode,
                "제목": art["title"],
                "가격": price_int,
                "등록시간": created,
                "판매자": art["user"]["nickname"],
                "판매완료": "예" if sold else "아니오",
                "본문내용": art["content"],
                "링크": art["href"],
                "썸네일": art["thumbnail"]
            })

        df_mid = pd.DataFrame(all_rows)
        if not df_mid.empty:
            df_mid = df_mid.drop_duplicates(subset=["링크"]).reset_index(drop=True)
            result_container.dataframe(
                df_mid.drop(columns=["코드", "썸네일"], errors="ignore"),
                use_container_width=True
            )
        progress.progress((idx + 1) / total)

    st.session_state.is_searching = False
    st.session_state.results_df = df_mid

# --- 8) 결과 출력 & 카드뷰 & 다운로드 ---
df_final = st.session_state.results_df
if not df_final.empty:
    st.success(f"✅ 총 {len(df_final)}건 검색 완료")

    csv_data = df_final.drop(columns=["썸네일"], errors="ignore").to_csv(
        index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 결과 다운로드 (CSV)",
        data=csv_data,
        file_name="daangn_search_results.csv",
        mime="text/csv"
    )

    if mode == "지역 검색":
        st.markdown("### 카드 뷰")
        records = df_final.to_dict('records')
        for i in range(0, len(records), 3):
            cols = st.columns(3, gap="small")
            for j, rec in enumerate(records[i:i+3]):
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
