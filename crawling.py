import re, time, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

df = pd.read_csv("address_unique.csv", dtype=str)

driver = webdriver.Chrome()
driver.get("https://www.daangn.com/kr/")
time.sleep(2)
driver.find_element(By.CSS_SELECTOR, "button[data-gtm='gnb_location']").click()
time.sleep(1)

INPUT_CSS  = "input[aria-label='Search input']"
SUBMIT_CSS = "button[type='submit'][aria-label='Search']"
RESULT_A   = "section ul li a"

results = []

for _, row in df.iterrows():
    query = row["search_query"]
    tokens = query.split()

    # 검색창에 입력 & 검색
    inp = driver.find_element(By.CSS_SELECTOR, INPUT_CSS)
    inp.clear()
    inp.send_keys(query)
    time.sleep(0.2)
    driver.find_element(By.CSS_SELECTOR, SUBMIT_CSS).click()

    # AJAX 반영 대기 + 재시도
    data = []
    start = time.time()
    # 검사할 토큰: 두 번째가 있으면 두 번째, 없으면 첫 번째
    check_tok = tokens[1] if len(tokens) > 1 else tokens[0]

    while time.time() - start < 5:
        data = driver.execute_script("""
            return Array.from(
                document.querySelectorAll(arguments[0])
            ).map(a=>({text:a.innerText.trim(), href:a.href}));
        """, RESULT_A)

        # check_tok이 하나라도 포함되면 통과
        if any(check_tok in item["text"] for item in data):
            break
        time.sleep(3)
    else:
        print(f"[!] 결과 불완전 (timeout): {query}")

    # 수집된 data 파싱
    for item in data:
        text = item["text"]
        href = item["href"]
        region_name = text.split(",")[-1].strip()
        m = re.search(r"in=[^/]+-(\d+)", href)
        if not m:
            continue
        code = m.group(1)
        results.append({
            "검색어":       query,
            "region_name": region_name,
            "region_code": code,
            "link_text":   text,
            "link_href":   href
        })

    inp.clear()
    time.sleep(3)

driver.quit()

pd.DataFrame(results).to_csv(
    "address_with_all_codes.csv",
    index=False,
    encoding="utf-8-sig"
)
print("완료: address_with_all_codes.csv 생성")
