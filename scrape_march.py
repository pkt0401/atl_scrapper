"""
SK AX AI Talent Lab 문의게시판 스크래퍼 - 3월 이후 데이터만 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 최신 게시글부터 순서대로 수집
- 2026-03-01 미만(2월 이전) 게시글 만나면 즉시 중단
- 출력 포맷: inquiry_all.json / inquiry_comment_all.json 동일 형식

출력:
  inquiry_new.json          ← inquiry_all.json 형식
  inquiry_comment_new.json  ← inquiry_comment_all.json 형식
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import json
import time
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

# ━━━━━━━━━━ 설정 ━━━━━━━━━━
BASE_URL = "https://aitalentlab.skax.co.kr"
INQUIRY_URL = f"{BASE_URL}/inquiry"
CUTOFF_DATE = datetime(2026, 3, 1)   # 이 날짜 미만이면 수집 중단
MAX_PAGES = 50                         # 안전 상한 (실제로는 날짜 필터로 먼저 중단됨)
DELAY = 2

USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")


# ━━━━━━━━━━ 드라이버 ━━━━━━━━━━

def init_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # 네트워크 로그 캡처를 위한 설정
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except ImportError:
        return webdriver.Chrome(options=options)


def login(driver):
    driver.get(BASE_URL)
    time.sleep(2)

    if "login" in driver.current_url.lower():
        try:
            driver.find_element(By.CSS_SELECTOR, "input[type='text']").send_keys(USERNAME)
            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            time.sleep(3)
            if "login" not in driver.current_url.lower():
                print("✅ 자동 로그인 완료")
                driver.get(INQUIRY_URL)
                time.sleep(2)
                return
        except Exception:
            pass

    print("⚠️  브라우저에서 직접 로그인해주세요.")
    input("   로그인 완료 후 Enter >> ")
    driver.get(INQUIRY_URL)
    time.sleep(2)


# ━━━━━━━━━━ 날짜 파싱 ━━━━━━━━━━

def parse_date(date_str: str) -> datetime | None:
    """다양한 날짜 형식 파싱"""
    if not date_str:
        return None
    date_str = date_str.strip()
    # "2025. 12. 14." 형식 처리 (공백 정규화)
    date_str = re.sub(r'\s+', ' ', date_str).rstrip('.')
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
        "%Y. %m. %d %H:%M:%S",
        "%Y. %m. %d %H:%M",
        "%Y. %m. %d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # 숫자만 추출해서 시도
    nums = re.findall(r'\d+', date_str)
    if len(nums) >= 3:
        try:
            return datetime(int(nums[0]), int(nums[1]), int(nums[2]))
        except Exception:
            pass
    return None


def is_before_cutoff(date_str: str) -> bool:
    """CUTOFF_DATE 이전이면 True (수집 중단 대상)"""
    dt = parse_date(date_str)
    if dt is None:
        return False
    return dt < CUTOFF_DATE


# ━━━━━━━━━━ 모달 제어 ━━━━━━━━━━

def close_modal(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, "[class*='closeButton_hdlr3']")
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(1)
        return
    except NoSuchElementException:
        pass
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
    except Exception:
        pass


def is_modal_open(driver):
    try:
        el = driver.find_element(By.CSS_SELECTOR, "[class*='modalOverlay_hdlr3']")
        return el.is_displayed()
    except NoSuchElementException:
        return False


# ━━━━━━━━━━ 이미지 감지 ━━━━━━━━━━

def modal_has_images(driver) -> bool:
    """
    모달 내 이미지 존재 여부 확인
    - 본문/댓글에 <img> 태그 있거나
    - 첨부 이미지 영역(_images_hdlr3_)이 있으면 True
    """
    try:
        # 본문 이미지
        imgs = driver.find_elements(
            By.CSS_SELECTOR,
            "[class*='modalContent_hdlr3'] img"
        )
        # SVG/아이콘 제외 (실제 첨부 이미지만)
        for img in imgs:
            src = img.get_attribute("src") or ""
            if src and not src.startswith("data:image/svg"):
                return True

        # 첨부 이미지 영역
        attach_area = driver.find_elements(
            By.CSS_SELECTOR, "[class*='images_hdlr3']"
        )
        if attach_area:
            return True

    except Exception:
        pass
    return False


# ━━━━━━━━━━ 모달에서 게시글 상세 정보 추출 ━━━━━━━━━━

def extract_modal_detail(driver) -> dict:
    """
    모달에서 HTML 내용, 작성자, 날짜, 상태, 댓글 추출
    반환: {
        title, content_html, author_name, date_str, status, is_pinned,
        comments: [{content_html, author_name, date_str, is_admin}]
    }
    """
    result = {
        "title": "",
        "content_html": "",
        "author_name": "",
        "date_str": "",
        "status": "",
        "is_pinned": 0,
        "comments": [],
    }

    time.sleep(1.5)

    try:
        modal = driver.find_element(By.CSS_SELECTOR, "[class*='modalContent_hdlr3']")
    except NoSuchElementException:
        print("      ⚠️ 모달을 찾을 수 없음")
        return result

    # 제목
    try:
        title_el = modal.find_element(By.CSS_SELECTOR, "h2[class*='title_hdlr3']")
        result["title"] = title_el.text.strip()
    except NoSuchElementException:
        pass

    # 작성자, 날짜, 상태
    try:
        meta = modal.find_element(By.CSS_SELECTOR, "[class*='meta_hdlr3']")
        spans = meta.find_elements(By.TAG_NAME, "span")
        if len(spans) >= 1:
            result["author_name"] = spans[0].text.strip()
        if len(spans) >= 2:
            result["date_str"] = spans[1].text.strip()
        if len(spans) >= 3:
            result["status"] = spans[2].text.strip()
    except NoSuchElementException:
        pass

    # 질문 본문 HTML
    try:
        content_el = modal.find_element(By.CSS_SELECTOR, "[class*='content_hdlr3_609']")
        result["content_html"] = content_el.get_attribute("innerHTML")
    except NoSuchElementException:
        pass

    # 댓글 목록
    try:
        comment_els = modal.find_elements(
            By.CSS_SELECTOR,
            "[class*='commentsList_hdlr3'] > [class*='comment_hdlr3']"
        )
        if not comment_els:
            comment_content_els = modal.find_elements(
                By.CSS_SELECTOR, "[class*='commentContent_hdlr3']"
            )
            if comment_content_els:
                comment_els = [el.find_element(By.XPATH, "..") for el in comment_content_els]

        for cel in comment_els:
            comment = {
                "content_html": "",
                "author_name": "",
                "date_str": "",
                "is_admin": False,
            }

            # 작성자 + 관리자 여부
            try:
                author_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentAuthor_hdlr3']")
                full_author = author_el.text.strip()
                try:
                    badge = cel.find_element(By.CSS_SELECTOR, "[class*='adminBadge_hdlr3']")
                    comment["is_admin"] = True
                    comment["author_name"] = full_author.replace(badge.text.strip(), "").strip()
                except NoSuchElementException:
                    comment["author_name"] = full_author
            except NoSuchElementException:
                pass

            # 날짜
            try:
                date_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentDate_hdlr3']")
                comment["date_str"] = date_el.text.strip()
            except NoSuchElementException:
                pass

            # 댓글 HTML
            try:
                content_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentContent_hdlr3']")
                comment["content_html"] = content_el.get_attribute("innerHTML")
            except NoSuchElementException:
                pass

            if comment["content_html"]:
                result["comments"].append(comment)

    except Exception as e:
        print(f"      ⚠️ 댓글 파싱 실패: {e}")

    return result


def normalize_date(date_str: str) -> str:
    """날짜를 'YYYY-MM-DD HH:MM:SS' 형식으로 정규화"""
    dt = parse_date(date_str)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return date_str


# ━━━━━━━━━━ 메인 스크래핑 ━━━━━━━━━━

def get_total_pages(driver) -> int:
    """페이지네이션에서 총 페이지 수 파악"""
    try:
        btns = driver.find_elements(
            By.CSS_SELECTOR,
            "[class*='pagination'] button, [class*='paging'] button, "
            "[class*='page'] button, [class*='page'] a, [class*='page'] li"
        )
        max_page = 1
        for btn in btns:
            t = btn.text.strip()
            if t.isdigit():
                max_page = max(max_page, int(t))
        return max_page
    except Exception:
        return 1


def navigate_to_page(driver, page: int, current_page: int) -> bool:
    """특정 페이지로 이동. 성공 여부 반환."""
    if page == current_page:
        return True
    try:
        # 페이지 번호 버튼 찾아 클릭
        btns = driver.find_elements(
            By.CSS_SELECTOR,
            "[class*='pagination'] button, [class*='paging'] button, "
            "[class*='page'] button, [class*='page'] a"
        )
        for btn in btns:
            if btn.text.strip() == str(page):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                return True

        # 이전/다음 버튼으로 이동
        if page < current_page:
            for btn in driver.find_elements(By.CSS_SELECTOR, "[class*='prev'], [class*='before']"):
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    return True
        else:
            for btn in driver.find_elements(By.CSS_SELECTOR, "[class*='next']"):
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    return True
    except Exception as e:
        print(f"  ⚠️ 페이지 이동 실패: {e}")
    return False


def scrape_march_onwards(driver):
    """
    inquiry_all.json 형식의 inquiries 리스트와
    inquiry_comment_all.json 형식의 comments 리스트를 반환
    - 1페이지(최신)부터 순서대로 탐색
    - 공지(pinned) 게시글은 스킵
    - 2026-03-01 미만 게시글 만나면 중단
    """
    inquiries = []
    comments = []

    # ID 카운터 (기존 최대 ID 이후부터 시작)
    # inquiry_all.json의 마지막 id = 102, inquiry_comment_all.json의 마지막 id = 123
    inq_id = 103
    cmt_id = 124

    # 1페이지 로드 후 총 페이지 수 파악
    driver.get(INQUIRY_URL)
    time.sleep(2)
    total_pages = get_total_pages(driver)
    print(f"  📋 총 페이지 수: {total_pages}")

    current_page = 1
    stop_scraping = False

    for page in range(1, total_pages + 1):
        if stop_scraping:
            break

        print(f"\n{'='*50}")
        print(f"📄 페이지 {page}/{total_pages}")
        print(f"{'='*50}")

        # 페이지 이동 (1페이지는 이미 로드됨)
        if page != current_page:
            if not navigate_to_page(driver, page, current_page):
                print(f"  ⚠️ 페이지 {page} 이동 실패, 건너뜀")
                continue
        current_page = page

        if is_modal_open(driver):
            close_modal(driver)
            time.sleep(1)

        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        print(f"  → {len(rows)}개 게시글")

        if not rows:
            print("  ℹ️ 게시글 없음. 종료.")
            break

        for row_idx in range(len(rows)):
            try:
                if is_modal_open(driver):
                    close_modal(driver)
                    time.sleep(1)

                rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                if row_idx >= len(rows):
                    break

                row = rows[row_idx]
                row_text = row.text.strip()
                if not row_text or len(row_text) < 3:
                    continue

                # 테이블 셀에서 기본 정보 추출
                cells = row.find_elements(By.TAG_NAME, "td")
                status_text, title_text, author_text, date_text = "", "", "", ""

                if len(cells) >= 5:
                    status_text = cells[0].text.strip()
                    title_text  = cells[1].text.strip()
                    author_text = cells[2].text.strip()
                    date_text   = cells[4].text.strip()
                elif len(cells) >= 4:
                    status_text = cells[0].text.strip()
                    title_text  = cells[1].text.strip()
                    author_text = cells[2].text.strip()
                    date_text   = cells[3].text.strip()

                # ── 공지(pinned) 게시글 스킵 ──
                if "공지" in status_text:
                    print(f"\n    [{row_idx+1}] ⏭️  공지 스킵: '{title_text[:40]}'")
                    continue

                # ── 날짜 필터: 3월 미만이면 중단 ──
                if date_text and is_before_cutoff(date_text):
                    print(f"\n  🛑 날짜 '{date_text}' → 2026-03 미만. 수집 중단.")
                    stop_scraping = True
                    break

                print(f"\n    [{row_idx+1}/{len(rows)}] '{title_text[:50]}' ({date_text})")

                # 클릭해서 모달 열기
                try:
                    title_td = row.find_element(By.CSS_SELECTOR, "[class*='titleCol_hdlr3']")
                    driver.execute_script("arguments[0].click();", title_td)
                except NoSuchElementException:
                    driver.execute_script("arguments[0].click();", row)
                time.sleep(DELAY)

                # ── 이미지 있는 게시글 스킵 ──
                if modal_has_images(driver):
                    print(f"      ⏭️  이미지 포함 → 스킵")
                    close_modal(driver)
                    time.sleep(DELAY)
                    continue

                # 모달 내용 추출
                detail = extract_modal_detail(driver)

                # 날짜 결정 (모달 내 날짜가 더 정확)
                final_date = detail["date_str"] or date_text
                if final_date and is_before_cutoff(final_date):
                    print(f"  🛑 모달 날짜 '{final_date}' → 2026-03 미만. 수집 중단.")
                    close_modal(driver)
                    stop_scraping = True
                    break

                norm_date = normalize_date(final_date)

                # ── inquiry_all.json 형식으로 저장 ──
                inquiry = {
                    "id": inq_id,
                    "title": detail["title"] or title_text,
                    "content": detail["content_html"],
                    "author_id": None,           # UI에서 integer ID 불가 → null
                    "author_name": detail["author_name"] or author_text,
                    "file_ids": "[]",
                    "group_id": None,
                    "status": "closed" if "답변완료" in (detail["status"] or status_text) else "open",
                    "is_pinned": 0,
                    "create_dt": norm_date,
                    "update_dt": norm_date,
                }
                inquiries.append(inquiry)

                print(f"      ✅ 문의 #{inq_id} 저장 | 날짜: {norm_date}")

                # ── inquiry_comment_all.json 형식으로 댓글 저장 ──
                for c in detail["comments"]:
                    c_date = normalize_date(c["date_str"]) if c["date_str"] else norm_date
                    comment = {
                        "id": cmt_id,
                        "inquiry_id": inq_id,
                        "content": c["content_html"],
                        "author_id": None,
                        "author_name": c["author_name"],
                        "file_ids": None,
                        "is_admin": 1 if c["is_admin"] else 0,
                        "create_dt": c_date,
                        "update_dt": c_date,
                    }
                    comments.append(comment)
                    cmt_id += 1

                print(f"      댓글: {len(detail['comments'])}개")

                inq_id += 1

                close_modal(driver)
                time.sleep(DELAY)

            except Exception as e:
                print(f"    ⚠️ 행 {row_idx+1} 실패: {e}")
                close_modal(driver)
                time.sleep(DELAY)

        print(f"\n  ✓ 누적 문의: {len(inquiries)}건, 댓글: {len(comments)}건")

    return inquiries, comments


# ━━━━━━━━━━ 저장 ━━━━━━━━━━

def save_results(inquiries: list, comments: list):
    out_dir = "c:\\atl_scrapper"

    inq_path = os.path.join(out_dir, "inquiry_new.json")
    with open(inq_path, "w", encoding="utf-8") as f:
        json.dump(inquiries, f, ensure_ascii=False, indent=2)
    print(f"  📦 {inq_path} ({len(inquiries)}건)")

    cmt_path = os.path.join(out_dir, "inquiry_comment_new.json")
    with open(cmt_path, "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)
    print(f"  📦 {cmt_path} ({len(comments)}건)")


# ━━━━━━━━━━ 메인 ━━━━━━━━━━

def main():
    driver = init_driver()
    try:
        login(driver)
        print(f"\n✅ {INQUIRY_URL} 접속 완료")
        print(f"📅 수집 기준: {CUTOFF_DATE.strftime('%Y-%m-%d')} 이후 게시글만\n")

        inquiries, comments = scrape_march_onwards(driver)

        if inquiries:
            print(f"\n{'='*50}")
            print(f"💾 저장 중...")
            save_results(inquiries, comments)
            print(f"\n🎉 완료! 문의: {len(inquiries)}건 / 댓글: {len(comments)}건")
        else:
            print("\n⚠️ 수집된 데이터가 없습니다.")

    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
