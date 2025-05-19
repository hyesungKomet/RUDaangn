import pandas as pd

# 1) TSV 로드 및 '존재'인 법정동만 필터
df = pd.read_csv("address.tsv", sep="\t", encoding="cp949", dtype=str)
df = df[df["폐지여부"] == "존재"].reset_index(drop=True)

# 2) '직할'→'광역', '울산시'→'울산광역시' 치환
df["법정동명"] = df["법정동명"] \
    .str.replace("직할", "광역", regex=False) \
    .str.replace("울산시", "울산광역시", regex=False) \
    .str.replace("전북특별자치도", "전라북도", regex=False)

# 3) 검색어 생성 함수
def format_name(full_name):
    parts = full_name.split()
    # 세종특별자치시는 토큰 1개만
    if parts[0] == "세종특별자치시":
        return parts[0]
    # 광역시/특별시: 토큰 2개
    if parts[0].endswith(("광역시", "특별시")):
        return " ".join(parts[:2])
    # 3번째 토큰이 동/읍/면 → 도+시까지만
    if len(parts) >= 3 and parts[2].endswith(("동", "읍", "면", "가")):
        return " ".join(parts[:2])
    # 3번째 토큰이 구/군 → 도+시+구(군)까지
    if len(parts) >= 3 and parts[2].endswith(("구", "군")):
        return " ".join(parts[:3])
    # 그 외 앞 3토큰
    return " ".join(parts[:3])

df["search_query"] = df["법정동명"].map(format_name)

# 4) 중복 제거 (search_query 기준)
unique_df = df.drop_duplicates(subset=["search_query"]).reset_index(drop=True)

# 5) 결과 저장
#    —법정동명과 대응 검색어를 함께 보고 싶다면 아래처럼
unique_df[["법정동명", "search_query"]] \
    .to_csv("address_unique.csv", index=False, encoding="utf-8-sig")

#    —만약 검색어만 필요하다면:
# unique_df[["search_query"]] \
#     .to_csv("address_unique.csv", index=False, encoding="utf-8-sig")
