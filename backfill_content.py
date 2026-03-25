"""
inquiry_all.json에서 content가 비어있는 항목의 본문을 채우는 백필 스크립트
- 사이트를 순회하며 빈 content 항목을 찾아 채움
- title + create_dt 기준으로 매칭
"""

from scrape_update import (
    init_driver, login, INQUIRY_URL, DELAY,
    get_total_pages, navigate_to_page, is_modal_open, close_modal,
    modal_has_images, flush_network_logs, get_api_data,
    extract_modal_detail, normalize_date, parse_date,
    ALL_INQ_PATH,
)
import json
import time
import re
from datetime import datetime


def load_empty_entries():
    """content가 비어있는 항목들을 로드"""
    with open(ALL_INQ_PATH, encoding="utf-8") as f:
        all_data = json.load(f)

    empty = {d["id"]: d for d in all_data if not d.get("content")}
    print(f"전체 {len(all_data)}건 중 content 비어있는 항목: {len(empty)}건")

    # 매칭용 lookup: (title, date_prefix) -> id
    lookup = {}
    for d in empty.values():
        # 날짜의 날짜 부분만 사용 (시간은 무시 - 테이블에 시간이 안 보일 수 있음)
        date_key = d["create_dt"][:10] if d.get("create_dt") else ""
        key = (d["title"].strip(), date_key)
        lookup[key] = d["id"]

    return all_data, empty, lookup


def backfill(driver, all_data, empty, lookup):
    """페이지를 순회하며 빈 content를 채움"""
    driver.get(INQUIRY_URL)
    time.sleep(2)
    total_pages = get_total_pages(driver)
    print(f"총 페이지 수: {total_pages}")

    filled_count = 0
    remaining = len(empty)
    current_page = 1

    # 빈 항목의 날짜 범위 파악 (범위 밖이면 조기 종료)
    dates = [d["create_dt"] for d in empty.values() if d.get("create_dt")]
    if dates:
        min_date = min(dates)[:10]
        print(f"채울 항목 날짜 범위: {min_date} ~ {max(dates)[:10]}")
    else:
        min_date = None

    for page in range(1, total_pages + 1):
        if remaining <= 0:
            print(f"\n모든 빈 항목 채움 완료!")
            break

        print(f"\n{'='*50}")
        print(f"페이지 {page}/{total_pages} (남은 빈 항목: {remaining})")
        print(f"{'='*50}")

        if page != current_page:
            if not navigate_to_page(driver, page, current_page):
                print(f"  페이지 {page} 이동 실패, 건너뜀")
                continue
        current_page = page

        if is_modal_open(driver):
            close_modal(driver)
            time.sleep(1)

        rows = driver.find_elements_by_css_selector("table tbody tr") if hasattr(driver, 'find_elements_by_css_selector') else driver.find_elements("css selector", "table tbody tr")
        print(f"  {len(rows)}개 게시글")

        if not rows:
            break

        # 이 페이지의 날짜가 빈 항목 범위보다 이전이면 종료
        page_past_range = False

        for row_idx in range(len(rows)):
            try:
                if is_modal_open(driver):
                    close_modal(driver)
                    time.sleep(1)

                from selenium.webdriver.common.by import By
                rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                if row_idx >= len(rows):
                    break

                row = rows[row_idx]
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 4:
                    continue

                status_text = cells[0].text.strip()
                title_text = cells[1].text.strip()
                date_text = cells[-1].text.strip() if len(cells) >= 5 else cells[3].text.strip()

                # 공지 스킵
                if "공지" in status_text:
                    continue

                # 날짜에서 날짜 부분 추출
                date_key = normalize_date(date_text)[:10] if date_text else ""

                # 이 행이 빈 content 항목과 매칭되는지 확인
                key = (title_text.strip(), date_key)
                matched_id = lookup.get(key)

                if matched_id is None:
                    # 제목만으로도 매칭 시도 (날짜 형식이 다를 수 있음)
                    for (t, d), eid in lookup.items():
                        if t == title_text.strip() and eid in empty:
                            matched_id = eid
                            break

                if matched_id is None:
                    # 이 항목은 이미 content가 있거나 매칭 안 됨
                    # 날짜가 범위 밖인지 체크
                    if min_date and date_key and date_key < min_date:
                        page_past_range = True
                    continue

                if matched_id not in empty:
                    continue

                print(f"\n    [{row_idx+1}] 매칭: id={matched_id} '{title_text[:40]}' ({date_text})")

                # 클릭해서 모달 열기
                flush_network_logs(driver)
                try:
                    title_td = row.find_element(By.CSS_SELECTOR, "[class*='titleCol_hdlr3']")
                    driver.execute_script("arguments[0].click();", title_td)
                except Exception:
                    driver.execute_script("arguments[0].click();", row)
                time.sleep(DELAY)

                # API + 모달에서 content 추출
                api_ts = get_api_data(driver)
                detail = extract_modal_detail(driver)

                content = api_ts.get("content") or detail["content_html"]

                if content:
                    # all_data에서 해당 항목 업데이트
                    for item in all_data:
                        if item["id"] == matched_id:
                            item["content"] = content
                            break
                    del empty[matched_id]
                    remaining -= 1
                    filled_count += 1
                    print(f"      채움! (content 길이: {len(content)})")
                else:
                    print(f"      content를 가져오지 못함")

                close_modal(driver)
                time.sleep(DELAY)

            except Exception as e:
                print(f"    행 {row_idx+1} 실패: {e}")
                if is_modal_open(driver):
                    close_modal(driver)
                time.sleep(DELAY)

        if page_past_range and remaining > 0:
            # 남은 빈 항목이 있지만 날짜 범위를 벗어남
            print(f"\n  날짜 범위 밖 도달, 하지만 아직 {remaining}개 남음 - 계속 진행")

    return filled_count


def main():
    all_data, empty, lookup = load_empty_entries()
    if not empty:
        print("채울 항목이 없습니다!")
        return

    driver = init_driver()
    try:
        login(driver)
        print(f"\n{INQUIRY_URL} 접속 완료\n")

        filled = backfill(driver, all_data, empty, lookup)

        # 저장
        with open(ALL_INQ_PATH, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"\n완료! {filled}건 content 채움, 남은 빈 항목: {len(empty)}건")
        print(f"저장: {ALL_INQ_PATH}")

    except Exception as e:
        # 중간 저장 (에러 발생해도 지금까지 채운 것은 저장)
        with open(ALL_INQ_PATH, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"\n에러 발생: {e}")
        print(f"중간 저장 완료 ({ALL_INQ_PATH})")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
