"""
SK AX AI Talent Lab 문의게시판 스크래퍼 - 증분 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 기존 inquiry_all.json / inquiry_comment_all.json 읽어서
  이미 수집된 최신 날짜 이후 게시글만 추가 수집
- 공지(pinned) 게시글, 이미지 포함 게시글 스킵

출력:
  inquiry_all.json          ← 기존 + 신규 (날짜 오름차순)
  inquiry_comment_all.json  ← 기존 + 신규 (날짜 오름차순)
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
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
FALLBACK_CUTOFF = datetime(2026, 3, 1)  # 기존 파일 없을 때 기본 컷오프
MAX_PAGES = 50
DELAY = 2

INQ_PATH = os.path.join("c:\\atl_scrapper", "inquiry_new.json")
CMT_PATH = os.path.join("c:\\atl_scrapper", "inquiry_comment_new.json")

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


def is_already_collected(date_str: str, latest_dt: datetime) -> bool:
    """latest_dt 이하(이미 수집된 범위)면 True → 중단"""
    cleaned = re.sub(r'T', ' ', date_str)
    cleaned = re.sub(r'\.\d+', '', cleaned)
    cleaned = re.sub(r'[Zz]$', '', cleaned)
    cleaned = re.sub(r'[+-]\d{2}:\d{2}$', '', cleaned).strip()
    dt = parse_date(cleaned)
    if dt is None:
        return False
    return dt <= latest_dt


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


# ━━━━━━━━━━ 네트워크 API 응답 캡처 ━━━━━━━━━━

def flush_network_logs(driver):
    """쌓인 네트워크 로그를 비워서 다음 캡처를 깔끔하게 준비"""
    try:
        driver.get_log("performance")
    except Exception:
        pass


def get_api_data(driver) -> dict:
    """
    모달 클릭 후 발생한 네트워크 요청에서 문의 전체 데이터 추출.
    반환: {
        "create_dt", "update_dt",
        "comments": [{create_dt, update_dt, content, author_name, is_admin}, ...]
    }
    찾지 못하면 빈 dict 반환.
    """
    result = {}
    try:
        logs = driver.get_log("performance")
        for entry in reversed(logs):
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") != "Network.responseReceived":
                    continue
                url = msg["params"]["response"]["url"]
                if not any(k in url for k in ["/inquiry", "/inquiries", "/board", "/post", "/question"]):
                    continue
                content_type = msg["params"]["response"].get("mimeType", "")
                if "json" not in content_type and "javascript" not in content_type:
                    continue
                req_id = msg["params"]["requestId"]
                try:
                    body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                    if not body or not body.get("body"):
                        continue
                    data = json.loads(body["body"])
                    if isinstance(data, dict):
                        item = data.get("data") or data.get("result") or data.get("inquiry") or data
                        if isinstance(item, dict) and "create_dt" in item:
                            result["create_dt"] = item.get("create_dt", "")
                            result["update_dt"] = item.get("update_dt", "")
                            comments_raw = (
                                item.get("comments") or item.get("answers") or
                                data.get("comments") or []
                            )
                            result["comments"] = [
                                {
                                    "create_dt": c.get("create_dt", ""),
                                    "update_dt": c.get("update_dt", ""),
                                    # 댓글 본문: 여러 키 이름 시도
                                    "content": (
                                        c.get("content") or c.get("body") or
                                        c.get("text") or c.get("message") or ""
                                    ),
                                    # 작성자: 여러 키 이름 시도
                                    "author_name": (
                                        c.get("author_name") or c.get("username") or
                                        c.get("writer") or c.get("name") or
                                        c.get("user", {}).get("name", "") or ""
                                    ),
                                    "is_admin": int(bool(
                                        c.get("is_admin") or c.get("isAdmin") or
                                        c.get("role") == "admin"
                                    )),
                                }
                                for c in comments_raw if isinstance(c, dict)
                            ]
                            return result
                except Exception:
                    continue
            except Exception:
                continue
    except Exception:
        pass
    return result


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

    # 여러 선택자 순서대로 시도
    modal = None
    for sel in [
        "[class*='modalContent_hdlr3']",
        "[class*='modalInner_hdlr3']",
        "[class*='modalBody_hdlr3']",
        "[class*='Modal'] [class*='content']",
        "[class*='modal'] [class*='content']",
        "[role='dialog']",
    ]:
        try:
            modal = driver.find_element(By.CSS_SELECTOR, sel)
            break
        except NoSuchElementException:
            continue

    if modal is None:
        print("      ⚠️ 모달을 찾을 수 없음 (선택자 미매칭)")
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
    """날짜를 'YYYY-MM-DD HH:MM:SS' 형식으로 정규화
    ISO 8601 (2026-03-11T14:32:10Z, +09:00 등) 포함 처리
    """
    if not date_str:
        return date_str
    # T 구분자 → 공백, 타임존(Z, +00:00 등) 제거
    cleaned = re.sub(r'T', ' ', date_str)
    cleaned = re.sub(r'\.\d+', '', cleaned)       # 밀리초 제거
    cleaned = re.sub(r'[Zz]$', '', cleaned)       # Z 제거
    cleaned = re.sub(r'[+-]\d{2}:\d{2}$', '', cleaned)  # +09:00 제거
    cleaned = cleaned.strip()
    dt = parse_date(cleaned)
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


ALL_INQ_PATH = os.path.join("c:\\atl_scrapper", "inquiry_all.json")
ALL_CMT_PATH = os.path.join("c:\\atl_scrapper", "inquiry_comment_all.json")


def load_existing_data():
    """
    컷오프·ID 시작값: inquiry_all.json 기준 (이미 머지된 전체 데이터)
    저장 대상: inquiry_new.json (scrape_update 결과물, 나중에 merge_json으로 합침)
    """
    existing_inq, existing_cmt = [], []
    start_inq_id = 1
    start_cmt_id = 1
    latest_dt = FALLBACK_CUTOFF

    # 컷오프 및 ID 기준: _all.json
    if os.path.exists(ALL_INQ_PATH):
        with open(ALL_INQ_PATH, encoding="utf-8") as f:
            all_inq = json.load(f)
        if all_inq:
            start_inq_id = max(d["id"] for d in all_inq) + 1
            latest_str = max(d["create_dt"] for d in all_inq)
            cleaned = re.sub(r'T', ' ', latest_str)
            cleaned = re.sub(r'\.\d+|[Zz]$', '', cleaned)
            cleaned = re.sub(r'[+-]\d{2}:\d{2}$', '', cleaned).strip()
            dt = parse_date(cleaned)
            if dt:
                latest_dt = dt

    if os.path.exists(ALL_CMT_PATH):
        with open(ALL_CMT_PATH, encoding="utf-8") as f:
            all_cmt = json.load(f)
        if all_cmt:
            start_cmt_id = max(d["id"] for d in all_cmt) + 1

    # 이미 이번 회차에 수집된 _new.json이 있으면 이어서
    if os.path.exists(INQ_PATH):
        with open(INQ_PATH, encoding="utf-8") as f:
            existing_inq = json.load(f)
        if existing_inq:
            start_inq_id = max(d["id"] for d in existing_inq) + 1

    if os.path.exists(CMT_PATH):
        with open(CMT_PATH, encoding="utf-8") as f:
            existing_cmt = json.load(f)
        if existing_cmt:
            start_cmt_id = max(d["id"] for d in existing_cmt) + 1

    return existing_inq, existing_cmt, start_inq_id, start_cmt_id, latest_dt


def scrape_march_onwards(driver, start_inq_id: int, start_cmt_id: int, latest_dt: datetime):
    """
    inquiry_all.json 형식의 inquiries 리스트와
    inquiry_comment_all.json 형식의 comments 리스트를 반환
    - 1페이지(최신)부터 순서대로 탐색
    - 공지(pinned) 게시글, 이미지 포함 게시글 스킵
    - latest_dt 이하 게시글 만나면 중단 (이미 수집된 것)
    """
    inquiries = []
    comments = []

    inq_id = start_inq_id
    cmt_id = start_cmt_id

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

                # ── 날짜 필터: 이미 수집된 범위면 중단 (테이블 날짜로 사전 체크) ──
                if date_text and is_already_collected(date_text, latest_dt):
                    print(f"\n  🛑 날짜 '{date_text}' → 이미 수집된 범위. 중단.")
                    stop_scraping = True
                    break

                print(f"\n    [{row_idx+1}/{len(rows)}] '{title_text[:50]}' ({date_text})")

                # 클릭 전 네트워크 로그 초기화
                flush_network_logs(driver)

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

                # 네트워크 API 응답에서 문의 전체 데이터 추출
                api_ts = get_api_data(driver)

                # 모달 내용 추출
                detail = extract_modal_detail(driver)

                # 날짜 결정: API 응답 > 모달 텍스트 > 테이블 텍스트
                ui_date = detail["date_str"] or date_text
                if api_ts.get("create_dt"):
                    create_dt = api_ts["create_dt"]
                    update_dt = api_ts.get("update_dt") or create_dt
                    print(f"      🕐 API 타임스탬프: {create_dt}")
                else:
                    create_dt = normalize_date(ui_date)
                    update_dt = create_dt

                # 날짜 필터 (API 날짜로 재확인)
                if is_already_collected(create_dt, latest_dt):
                    print(f"  🛑 날짜 '{create_dt}' → 이미 수집된 범위. 중단.")
                    close_modal(driver)
                    stop_scraping = True
                    break

                # ── inquiry_all.json 형식으로 저장 ──
                inquiry = {
                    "id": inq_id,
                    "title": detail["title"] or title_text,
                    "content": detail["content_html"],
                    "author_id": None,
                    "author_name": detail["author_name"] or author_text,
                    "file_ids": "[]",
                    "group_id": None,
                    "status": "closed" if "답변완료" in (detail["status"] or status_text) else "open",
                    "is_pinned": 0,
                    "create_dt": create_dt,
                    "update_dt": update_dt,
                }
                inquiries.append(inquiry)

                print(f"      ✅ 문의 #{inq_id} 저장 | {create_dt}")

                # ── inquiry_comment_all.json 형식으로 댓글 저장 ──
                # API 댓글 우선, 없으면 모달 파싱 결과 사용
                api_comments = api_ts.get("comments", [])
                modal_comments = detail["comments"]

                # API 댓글에 content가 있으면 API 댓글 사용
                api_has_content = any(c.get("content") for c in api_comments)

                if api_has_content:
                    # API 응답 기반으로 댓글 저장
                    for ac in api_comments:
                        if not ac.get("content"):
                            continue
                        c_create = normalize_date(ac["create_dt"]) if ac.get("create_dt") else create_dt
                        c_update = normalize_date(ac["update_dt"]) if ac.get("update_dt") else c_create
                        comment = {
                            "id": cmt_id,
                            "inquiry_id": inq_id,
                            "content": ac["content"],
                            "author_id": None,
                            "author_name": ac.get("author_name", ""),
                            "file_ids": None,
                            "is_admin": ac.get("is_admin", 0),
                            "create_dt": c_create,
                            "update_dt": c_update,
                        }
                        comments.append(comment)
                        cmt_id += 1
                    print(f"      댓글: {len(api_comments)}개 (API)")
                else:
                    # 모달 파싱 결과 기반으로 댓글 저장
                    for i, c in enumerate(modal_comments):
                        if i < len(api_comments) and api_comments[i].get("create_dt"):
                            c_create = normalize_date(api_comments[i]["create_dt"])
                            c_update = normalize_date(api_comments[i].get("update_dt") or api_comments[i]["create_dt"])
                        else:
                            c_create = normalize_date(c["date_str"]) if c["date_str"] else create_dt
                            c_update = c_create
                        comment = {
                            "id": cmt_id,
                            "inquiry_id": inq_id,
                            "content": c["content_html"],
                            "author_id": None,
                            "author_name": c["author_name"],
                            "file_ids": None,
                            "is_admin": 1 if c["is_admin"] else 0,
                            "create_dt": c_create,
                            "update_dt": c_update,
                        }
                        comments.append(comment)
                        cmt_id += 1
                    print(f"      댓글: {len(modal_comments)}개 (모달)")

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

def save_results(new_inquiries: list, new_comments: list,
                 existing_inq: list, existing_cmt: list):
    """신규 데이터를 합쳐서 날짜 오름차순으로 저장"""
    combined_inq = existing_inq + new_inquiries
    combined_inq.sort(key=lambda d: d.get("create_dt") or "")

    combined_cmt = existing_cmt + new_comments
    combined_cmt.sort(key=lambda c: c.get("create_dt") or "")

    with open(INQ_PATH, "w", encoding="utf-8") as f:
        json.dump(combined_inq, f, ensure_ascii=False, indent=2)
    print(f"  📦 {INQ_PATH}  신규 {len(new_inquiries)}건 추가 → 총 {len(combined_inq)}건")

    with open(CMT_PATH, "w", encoding="utf-8") as f:
        json.dump(combined_cmt, f, ensure_ascii=False, indent=2)
    print(f"  📦 {CMT_PATH}  신규 {len(new_comments)}건 추가 → 총 {len(combined_cmt)}건")


# ━━━━━━━━━━ 메인 ━━━━━━━━━━

def main():
    existing_inq, existing_cmt, start_inq_id, start_cmt_id, latest_dt = load_existing_data()
    print(f"📅 수집 기준: '{latest_dt.strftime('%Y-%m-%d %H:%M:%S')}' 이후 게시글만")
    print(f"🔢 ID 시작: 문의 #{start_inq_id} / 댓글 #{start_cmt_id}")
    print(f"💡 수집 후 merge_json.py를 실행해서 inquiry_all.json에 반영하세요.\n")

    driver = init_driver()
    try:
        login(driver)
        print(f"\n✅ {INQUIRY_URL} 접속 완료\n")

        new_inq, new_cmt = scrape_march_onwards(
            driver, start_inq_id, start_cmt_id, latest_dt
        )

        if new_inq:
            print(f"\n{'='*50}")
            print(f"💾 저장 중...")
            save_results(new_inq, new_cmt, existing_inq, existing_cmt)
            print(f"\n🎉 완료! 신규 문의: {len(new_inq)}건 / 댓글: {len(new_cmt)}건")
        else:
            print("\n⚠️ 새로 수집된 데이터가 없습니다. (이미 최신 상태)")

    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
