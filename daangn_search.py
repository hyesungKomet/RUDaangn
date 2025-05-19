# streamlit_app.py
import streamlit as st
import pandas as pd
import requests

# 페이지 레이아웃
st.set_page_config(layout="wide")
st.title("ARE YOU DAANGN?")

# --- 세션 상태 플래그 ---
if "is_searching" not in st.session_state:
    st.session_state.is_searching = False
if "stop_search" not in st.session_state:
    st.session_state.stop_search = False

# --- 1) 지역 코드 CSV 로드 ---
@st.cache_data
def load_regions():
    df = pd.read_csv("address_with_all_codes.csv", dtype=str)
    df["광역"] = df["검색어"].map(lambda x: x.split()[0])
    MAJORS = [
        "서울특별시","부산광역시","대구광역시","인천광역시","광주광역시",
        "대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도",
        "충청북도","충청남도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"
    ]
    return df, MAJORS

regions_df, MAJORS = load_regions()

# --- 2) 검색 모드 & 입력 영역 ---
mode_col, input_col, key_col = st.columns([1,4,3])
with mode_col:
    mode = st.radio("🔎 모드", ["전국 검색", "지역 검색"], index=1, horizontal=True)
with input_col:
    item = st.text_input("찾을 물품 (ex: 노트북)", "")
with key_col:
    kws = st.text_input(
        "핵심 키워드 - 쉼표로 구분(ex: 게이밍, 3060)",
        help="ex: 게이밍, 3060  → 제목+내용에 포함된 내용만 검색합니다"
    )
    keywords = [w.strip().lower() for w in kws.split(",") if w.strip()]

# --- 3) 지역 검색 필터 ---
if mode == "지역 검색":
    with st.expander("지역 필터 설정", expanded=True):
        maj_sel = st.multiselect("광역 선택", MAJORS, default=MAJORS[:3])
        sub_df = regions_df[regions_df["광역"].isin(maj_sel)]
        sub_opts = sorted(sub_df["검색어"].unique())
        sub_sel = st.multiselect("동/읍/면 선택 (비워두면 모두)", sub_opts)
        if not sub_sel:
            sub_sel = sub_opts.copy()
else:
    maj_sel = []
    sub_sel = []

# --- 4) 페이지네이션 ---
pag1, pag2 = st.columns(2)
with pag1:
    per_page = st.number_input("페이지당 항목 수", 5, 50, 10, 5)
with pag2:
    page = st.number_input("페이지 번호", 1, 100, 1, 1)

# --- 5) 내부 API 호출 함수 ---
@st.cache_data
def fetch_articles(region_tag, query, page, limit):
    url = "https://www.daangn.com/kr/buy-sell/"
    params = {
        "in":     region_tag,
        "search": query,
        "_data":  "routes/kr.buy-sell._index",
        "page":   page,
        "limit":  limit
    }
    headers = {
        "Accept":     "application/json, text/plain, */*",
        "Referer":    "https://www.daangn.com/kr/buy-sell/",
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(url, params=params, headers=headers)
    r.raise_for_status()
    return r.json()

# --- 6) 시작/중지 버튼 ---
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
    # 대상 지역 결정
    if mode == "전국 검색":
        regions_to_search = regions_df["검색어"].tolist()
    else:
        regions_to_search = sub_sel

    total = len(regions_to_search)
    progress = st.progress(0)
    result_container = st.empty()
    all_rows = []

    for idx, region in enumerate(regions_to_search):
        # 중지 플래그 체크
        if st.session_state.stop_search:
            st.warning("🛑 검색이 중지되었습니다.")
            break

        # region 코드, API 호출
        code = regions_df.loc[
            regions_df["검색어"] == region, "region_code"
        ].iat[0]
        tag = f"{region}-{code}"
        data = fetch_articles(tag, item, page, per_page)
        arts = data.get("allPage", {}).get("fleamarketArticles", [])

        for art in arts:
            text = (art["title"] + " " + art["content"]).lower()
            if keywords and not all(kw in text for kw in keywords):
                continue
            
            # 가격을 문자열 → 정수로 변환
            raw_price = art["price"]
            try:
                price_int = int(float(raw_price))
            except:
                price_int = None
            all_rows.append({
                "광역":      region.split()[0],
                "지역":      region,
                "제목":      art["title"],
                "가격":      price_int,
                "등록시간":  art["createdAt"],
                "판매자":    art["user"]["nickname"],
                "업로드지역": data["region"]["depth3RegionName"],
                "링크":      art["href"],
                "썸네일":    art["thumbnail"],
                "설명":      art["content"][:80] + "…"
            })

        # 중간 결과 렌더링
        df_p = pd.DataFrame(all_rows)
        if not df_p.empty:
            df_p["등록시간"] = pd.to_datetime(df_p["등록시간"])
        result_container.dataframe(df_p, use_container_width=True)

        progress.progress((idx + 1) / total)

    # 검색 완료 후 플래그 리셋
    st.session_state.is_searching = False

    # 최종 결과 처리
    if not all_rows:
        st.info("조건에 맞는 결과가 없습니다.")
    else:
        df_final = pd.DataFrame(all_rows)
        df_final["등록시간"] = pd.to_datetime(df_final["등록시간"])
        st.success(f"✅ 총 {len(df_final)}건 검색 완료")

        # 전국: 표 / 지역: 카드뷰
        if mode == "전국 검색":
            st.dataframe(df_final, use_container_width=True)
        else:
            st.markdown("### 카드 뷰")
            cols = st.columns(3, gap="small")
            for i, row in df_final.iterrows():
                c = cols[i % 3]
                with c:
                    st.image(row["썸네일"], use_container_width=True)
                    st.markdown(f"**{row['제목']}**")
                    st.markdown(f"- 💰 {row['가격']}원")
                    st.markdown(f"- 📍 {row['업로드지역']} / {row['지역']}")
                    st.markdown(f"- 🕒 {row['등록시간'].strftime('%Y-%m-%d %H:%M')}")
                    st.markdown(f"- 👤 {row['판매자']}")
                    st.markdown(f"[🔗 상세보기]({row['링크']})")
                    st.markdown("---")

        # CSV 다운로드
        csv = df_final.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 결과 다운로드 (CSV)",
            data=csv,
            file_name="daangn_search_results.csv",
            mime="text/csv"
        )
