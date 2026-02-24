"""
SK AX AI Talent Lab 문의게시판 스크래퍼 v4 (최종)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실제 HTML 구조 기반 정확한 파싱
출력:
  inquiry_output/
  ├── inquiry_data.csv          ← 엑셀용 (질문/답변 별도 컬럼)
  ├── inquiry_qa_pairs.jsonl    ← RAG 임베딩용
  ├── inquiry_full.json         ← 전체 원본
  └── images/                   ← 이미지 파일들

설치:
    pip install selenium pandas webdriver-manager beautifulsoup4 requests
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
import pandas as pd
import requests
import json
import time
import re
import os
from urllib.parse import urljoin
from dotenv import load_dotenv

load_dotenv(override=True)

# ━━━━━━━━━━ 설정 ━━━━━━━━━━
BASE_URL = "https://aitalentlab.skax.co.kr"
INQUIRY_URL = f"{BASE_URL}/inquiry"
TOTAL_PAGES = 2
DELAY = 2

OUTPUT_DIR = "inquiry_output"
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")

# 로그인 정보 (본인 계정으로 수정)
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")


# ━━━━━━━━━━ 초기화 ━━━━━━━━━━

def setup_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)


def init_driver():
    options = Options()
    # options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except ImportError:
        return webdriver.Chrome(options=options)


def login(driver):
    """로그인 (자동 → 수동 순서로 시도)"""
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

    # 수동 로그인
    print("⚠️  브라우저에서 직접 로그인해주세요.")
    input("   로그인 완료 후 Enter >> ")
    driver.get(INQUIRY_URL)
    time.sleep(2)


# ━━━━━━━━━━ 모달 제어 ━━━━━━━━━━
# 실제 클래스: _closeButton_hdlr3_434, _modalOverlay_hdlr3_296

def close_modal(driver):
    """모달 닫기"""
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


# ━━━━━━━━━━ 이미지 다운로드 ━━━━━━━━━━

def download_image_via_canvas(driver, img_element, filepath: str) -> bool:
    """
    blob: URL 이미지를 canvas를 통해 base64로 변환 후 저장
    blob: URL은 브라우저 메모리에만 존재하므로 requests로 다운로드 불가
    """
    try:
        # 이미지가 로드될 때까지 대기
        driver.execute_script("""
            return new Promise((resolve) => {
                const img = arguments[0];
                if (img.complete) resolve(true);
                else {
                    img.onload = () => resolve(true);
                    img.onerror = () => resolve(false);
                    setTimeout(() => resolve(false), 5000);
                }
            });
        """, img_element)
        time.sleep(0.5)

        # canvas로 이미지를 그려서 base64 추출
        base64_data = driver.execute_script("""
            const img = arguments[0];
            const canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth || img.width;
            canvas.height = img.naturalHeight || img.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            return canvas.toDataURL('image/png').split(',')[1];
        """, img_element)

        if base64_data:
            import base64
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(base64_data))
            return True
    except Exception as e:
        print(f"        ⚠️ canvas 변환 실패: {e}")

    return False


def download_image_via_fetch(driver, blob_url: str, filepath: str) -> bool:
    """
    blob: URL을 fetch API로 읽어서 base64로 변환 후 저장
    canvas 방식이 CORS로 실패할 경우 대안
    """
    try:
        base64_data = driver.execute_async_script("""
            const url = arguments[0];
            const callback = arguments[1];
            fetch(url)
                .then(r => r.blob())
                .then(blob => {
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const base64 = reader.result.split(',')[1];
                        callback(base64);
                    };
                    reader.readAsDataURL(blob);
                })
                .catch(err => callback(null));
        """, blob_url)

        if base64_data:
            import base64
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(base64_data))
            return True
    except Exception as e:
        print(f"        ⚠️ fetch 변환 실패: {e}")

    return False


def download_images(driver, post_id: str) -> list[dict]:
    """
    모달 내 이미지 다운로드
    - blob: URL → canvas 또는 fetch로 base64 변환 후 저장
    - data: URL → base64 디코딩
    - http/https URL → requests로 다운로드
    """
    downloaded = []
    try:
        # 질문 본문 내 이미지
        q_images = driver.find_elements(By.CSS_SELECTOR, "[class*='content_hdlr3_609'] img")
        # 질문 첨부 이미지 (별도 영역: _images_hdlr3_656)
        q_attached = driver.find_elements(By.CSS_SELECTOR, "[class*='images_hdlr3'] img")
        q_images = q_images + q_attached
        # 댓글의 이미지
        a_images = driver.find_elements(By.CSS_SELECTOR, "[class*='commentContent_hdlr3'] img")

        all_images = [(img, "question") for img in q_images] + [(img, "answer") for img in a_images]

        if not all_images:
            return downloaded

        seen = set()
        for idx, (img_el, location) in enumerate(all_images, 1):
            src = img_el.get_attribute("src") or ""
            if not src or src in seen or src.startswith("data:image/svg"):
                continue
            seen.add(src)

            alt = img_el.get_attribute("alt") or ""
            filename = f"post_{post_id}_img_{idx}.png"
            filepath = os.path.join(IMAGE_DIR, filename)
            success = False

            try:
                if src.startswith("blob:"):
                    # ── blob: URL 처리 ──
                    # 방법 1: canvas로 변환
                    success = download_image_via_canvas(driver, img_el, filepath)

                    # 방법 2: fetch API로 변환 (canvas 실패 시)
                    if not success:
                        success = download_image_via_fetch(driver, src, filepath)

                    # 방법 3: 스크린샷으로 캡처 (최후의 수단)
                    if not success:
                        img_el.screenshot(filepath)
                        success = True
                        print(f"        📷 스크린샷으로 캡처: {filename}")

                elif src.startswith("data:image"):
                    # ── data: URL 처리 ──
                    import base64
                    header, data = src.split(",", 1)
                    ext = header.split("/")[1].split(";")[0]
                    filename = f"post_{post_id}_img_{idx}.{ext}"
                    filepath = os.path.join(IMAGE_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(data))
                    success = True

                else:
                    # ── http/https URL 처리 ──
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = urljoin(BASE_URL, src)

                    ext = "png"
                    m = re.search(r'\.(png|jpg|jpeg|gif|webp|bmp)', src.lower())
                    if m:
                        ext = m.group(1)
                    filename = f"post_{post_id}_img_{idx}.{ext}"
                    filepath = os.path.join(IMAGE_DIR, filename)

                    cookies = driver.get_cookies()
                    session = requests.Session()
                    for c in cookies:
                        session.cookies.set(c["name"], c["value"])

                    resp = session.get(src, timeout=10, stream=True)
                    if resp.status_code == 200:
                        with open(filepath, "wb") as f:
                            for chunk in resp.iter_content(1024):
                                f.write(chunk)
                        success = True

                if success:
                    downloaded.append({
                        "filename": filename,
                        "original_url": src[:100] if not src.startswith("data:") else "data:image...",
                        "alt_text": alt,
                        "location": location,
                    })
                    print(f"        📷 {filename}")

            except Exception as e:
                print(f"        ⚠️ 이미지 {idx} 실패: {e}")

    except Exception as e:
        print(f"      ⚠️ 이미지 수집 실패: {e}")

    return downloaded


# ━━━━━━━━━━ 모달 내용 추출 (정확한 셀렉터) ━━━━━━━━━━

def extract_modal_content(driver, post_id: str) -> dict:
    """
    실제 HTML 구조 기반 파싱:
    ┌─ _modalContent_hdlr3_309
    │  ├─ _modalHeader_hdlr3_318
    │  │  ├─ h2._title_hdlr3_218          ← 제목
    │  │  └─ _meta_hdlr3_334
    │  │     ├─ span (작성자)
    │  │     ├─ span (날짜)
    │  │     └─ span._status (상태)
    │  └─ _modalBody_hdlr3_446
    │     ├─ _content_hdlr3_609           ← 질문 본문
    │     ├─ _images_hdlr3_656            ← 첨부 이미지 (blob: URL)
    │     │  └─ img._clickableImage_hdlr3_662
    │     └─ _commentsSection_hdlr3_671   ← 댓글 섹션
    │        └─ _commentsList_hdlr3_682
    │           └─ _comment_hdlr3_232 (반복, 운영자: +_adminComment_hdlr3_690)
    │              ├─ _commentAuthor_hdlr3_690 + _adminBadge (운영자)
    │              ├─ _commentDate_hdlr3_715
    │              └─ _commentContent_hdlr3_732
    """
    result = {
        "question_text": "",
        "question_author": "",
        "question_date": "",
        "status": "",
        "answers": [],
        "images": [],
    }

    time.sleep(1.5)

    # 이미지 먼저 다운로드
    result["images"] = download_images(driver, post_id)

    try:
        modal = driver.find_element(By.CSS_SELECTOR, "[class*='modalContent_hdlr3']")
    except NoSuchElementException:
        print("      ⚠️ 모달을 찾을 수 없음")
        return result

    # ── 헤더: 작성자, 날짜, 상태 ──
    try:
        meta = modal.find_element(By.CSS_SELECTOR, "[class*='meta_hdlr3']")
        spans = meta.find_elements(By.TAG_NAME, "span")
        if len(spans) >= 1:
            result["question_author"] = spans[0].text.strip()
        if len(spans) >= 2:
            result["question_date"] = spans[1].text.strip()
        if len(spans) >= 3:
            result["status"] = spans[2].text.strip()
    except NoSuchElementException:
        pass

    # ── 질문 본문 ──
    try:
        content_el = modal.find_element(By.CSS_SELECTOR, "[class*='content_hdlr3_609']")
        # innerHTML로 가져와서 이미지를 placeholder로 치환
        content_html = content_el.get_attribute("innerHTML")
        soup = BeautifulSoup(content_html, "html.parser")

        # 이미지 → placeholder
        img_idx = 0
        for img in soup.find_all("img"):
            img_idx += 1
            alt = img.get("alt", "")
            placeholder = f"[이미지: post_{post_id}_img_{img_idx}]"
            if alt:
                placeholder = f"[이미지: post_{post_id}_img_{img_idx}, 설명: {alt}]"
            img.replace_with(placeholder)

        result["question_text"] = soup.get_text(separator="\n", strip=True)
    except NoSuchElementException:
        pass

    # ── 댓글(답변) 목록 ──
    try:
        # _commentsList_hdlr3_682 내의 각 _comment_hdlr3_232
        comment_els = modal.find_elements(By.CSS_SELECTOR, "[class*='commentsList_hdlr3'] > [class*='comment_hdlr3']")

        if not comment_els:
            # 대안: 직접 comment 클래스 찾기 (commentsList 없이)
            comment_els = modal.find_elements(By.CSS_SELECTOR, "[class*='commentContent_hdlr3']")
            if comment_els:
                # commentContent만 찾은 경우, 부모로 올라가기
                comment_els = [el.find_element(By.XPATH, "..") for el in comment_els]

        for cel in comment_els:
            answer = {"author": "", "date": "", "text": "", "is_admin": False}

            # 작성자
            try:
                author_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentAuthor_hdlr3']")
                # 작성자 텍스트에서 "운영자" 배지 텍스트 제거
                full_author = author_el.text.strip()
                try:
                    badge = cel.find_element(By.CSS_SELECTOR, "[class*='adminBadge_hdlr3']")
                    answer["is_admin"] = True
                    answer["author"] = full_author.replace(badge.text.strip(), "").strip()
                except NoSuchElementException:
                    answer["author"] = full_author
            except NoSuchElementException:
                pass

            # 날짜
            try:
                date_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentDate_hdlr3']")
                answer["date"] = date_el.text.strip()
            except NoSuchElementException:
                pass

            # 내용
            try:
                content_el = cel.find_element(By.CSS_SELECTOR, "[class*='commentContent_hdlr3']")
                c_html = content_el.get_attribute("innerHTML")
                c_soup = BeautifulSoup(c_html, "html.parser")

                # 이미지 → placeholder
                for img in c_soup.find_all("img"):
                    alt = img.get("alt", "")
                    img.replace_with(f"[이미지]" if not alt else f"[이미지: {alt}]")

                answer["text"] = c_soup.get_text(separator="\n", strip=True)
            except NoSuchElementException:
                pass

            if answer["text"]:
                result["answers"].append(answer)

    except Exception as e:
        print(f"      ⚠️ 댓글 파싱 실패: {e}")

    return result


# ━━━━━━━━━━ 메인 스크래핑 ━━━━━━━━━━

def scrape_all(driver) -> list[dict]:
    all_data = []
    post_counter = 0

    for page in range(1, TOTAL_PAGES + 1):
        print(f"\n{'='*50}")
        print(f"📄 페이지 {page}/{TOTAL_PAGES}")
        print(f"{'='*50}")

        # 페이지 이동
        if page == 1:
            driver.get(INQUIRY_URL)
            time.sleep(2)
        else:
            try:
                page_btns = driver.find_elements(By.CSS_SELECTOR,
                    "[class*='pagination'] button, [class*='pagination'] a, "
                    "[class*='paging'] button, [class*='page'] button, "
                    "[class*='page'] a, [class*='page'] li")
                clicked = False
                for btn in page_btns:
                    if btn.text.strip() == str(page):
                        driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        break
                if not clicked:
                    for nb in driver.find_elements(By.CSS_SELECTOR, "[class*='next']"):
                        if nb.is_displayed():
                            driver.execute_script("arguments[0].click();", nb)
                            break
                time.sleep(2)
            except Exception as e:
                print(f"  ⚠️ 페이지 이동 실패: {e}")
                continue

        if is_modal_open(driver):
            close_modal(driver)
            time.sleep(1)

        # 게시글 행
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        print(f"  → {len(rows)}개 게시글")

        for row_idx in range(len(rows)):
            try:
                if is_modal_open(driver):
                    close_modal(driver)
                    time.sleep(1)

                # DOM 갱신 대비 행 다시 찾기
                rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                if row_idx >= len(rows):
                    break

                row = rows[row_idx]
                row_text = row.text.strip()
                if not row_text or len(row_text) < 3:
                    continue

                # 기본 정보 (테이블 셀)
                cells = row.find_elements(By.TAG_NAME, "td")
                status, title, author, date_str = "", "", "", ""

                # 실제 테이블 구조: 상태 | 제목 | 작성자 | 댓글 | 작성일
                if len(cells) >= 5:
                    status = cells[0].text.strip()
                    title = cells[1].text.strip()
                    author = cells[2].text.strip()
                    date_str = cells[4].text.strip()
                elif len(cells) >= 4:
                    status = cells[0].text.strip()
                    title = cells[1].text.strip()
                    author = cells[2].text.strip()
                    date_str = cells[3].text.strip()

                post_counter += 1
                post_id = str(post_counter)
                print(f"\n    [{row_idx+1}/{len(rows)}] #{post_id} '{title[:50]}'")

                # 클릭 (JavaScript)
                try:
                    title_td = row.find_element(By.CSS_SELECTOR, "[class*='titleCol_hdlr3']")
                    driver.execute_script("arguments[0].click();", title_td)
                except NoSuchElementException:
                    driver.execute_script("arguments[0].click();", row)
                time.sleep(DELAY)

                # 모달 내용 추출
                detail = extract_modal_content(driver, post_id)

                record = {
                    "post_id": post_id,
                    "status": detail.get("status") or status,
                    "title": title,
                    "question_author": detail.get("question_author") or author,
                    "question_date": detail.get("question_date") or date_str,
                    "question_text": detail.get("question_text", ""),
                    "answer_count": len(detail.get("answers", [])),
                    "answers": detail.get("answers", []),
                    "images": detail.get("images", []),
                    "image_filenames": ", ".join(
                        img["filename"] for img in detail.get("images", [])
                    ),
                }
                all_data.append(record)

                # 미리보기
                q = record["question_text"][:60].replace("\n", " ")
                print(f"      질문: {q}...")
                print(f"      답변: {record['answer_count']}개, 이미지: {len(record['images'])}개")
                for ans in record["answers"]:
                    admin = "🔵운영자 " if ans["is_admin"] else ""
                    a_preview = ans["text"][:50].replace("\n", " ")
                    print(f"        → {admin}{ans['author']}: {a_preview}...")

                close_modal(driver)
                time.sleep(DELAY)

            except Exception as e:
                print(f"    ⚠️ 행 {row_idx+1} 실패: {e}")
                close_modal(driver)
                time.sleep(DELAY)

        print(f"\n  ✓ 누적: {len(all_data)}건")

    return all_data


# ━━━━━━━━━━ 저장 ━━━━━━━━━━

def save_csv(data: list[dict]):
    rows = []
    for d in data:
        row = {
            "게시글ID": d["post_id"],
            "상태": d["status"],
            "제목": d["title"],
            "질문_작성자": d["question_author"],
            "질문_작성일": d["question_date"],
            "질문_내용": d["question_text"],
            "답변_수": d["answer_count"],
            "이미지_파일": d["image_filenames"],
        }

        # 개별 답변 컬럼 (최대 5개)
        for i in range(5):
            if i < len(d["answers"]):
                ans = d["answers"][i]
                admin = "[운영자] " if ans["is_admin"] else ""
                row[f"답변{i+1}_작성자"] = f"{admin}{ans['author']}"
                row[f"답변{i+1}_작성일"] = ans["date"]
                row[f"답변{i+1}_내용"] = ans["text"]
            else:
                row[f"답변{i+1}_작성자"] = ""
                row[f"답변{i+1}_작성일"] = ""
                row[f"답변{i+1}_내용"] = ""

        rows.append(row)

    df = pd.DataFrame(rows)
    path = os.path.join(OUTPUT_DIR, "inquiry_data.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  📊 CSV: {path} ({len(df)}건)")


def save_jsonl_for_rag(data: list[dict]):
    path = os.path.join(OUTPUT_DIR, "inquiry_qa_pairs.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for d in data:
            # 답변 합치기
            combined_answers = ""
            if d["answers"]:
                parts = []
                for ans in d["answers"]:
                    admin = "[운영자] " if ans["is_admin"] else ""
                    parts.append(f"{admin}{ans['author']}: {ans['text']}")
                combined_answers = "\n".join(parts)

            image_refs = [img["filename"] for img in d["images"]]

            doc = {
                "id": f"inquiry_{d['post_id']}",
                "metadata": {
                    "source": "aitalentlab_inquiry",
                    "post_id": d["post_id"],
                    "title": d["title"],
                    "status": d["status"],
                    "question_author": d["question_author"],
                    "question_date": d["question_date"],
                    "answer_count": d["answer_count"],
                    "has_images": len(d["images"]) > 0,
                    "image_files": image_refs,
                },
                "question": d["question_text"],
                "answer": combined_answers,
                "full_text": (
                    f"[제목] {d['title']}\n"
                    f"[질문] {d['question_text']}\n\n"
                    f"[답변]\n{combined_answers}"
                ),
            }
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"  📝 JSONL: {path} ({len(data)}건)")


def save_full_json(data: list[dict]):
    path = os.path.join(OUTPUT_DIR, "inquiry_full.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  📦 JSON: {path}")


# ━━━━━━━━━━ 메인 ━━━━━━━━━━

def main():
    setup_dirs()
    driver = init_driver()

    try:
        login(driver)
        print(f"✅ {INQUIRY_URL} 접속 완료\n")

        all_data = scrape_all(driver)

        if all_data:
            print(f"\n{'='*50}")
            print(f"💾 저장 중...")
            print(f"{'='*50}")

            save_csv(all_data)
            save_jsonl_for_rag(all_data)
            save_full_json(all_data)

            total_images = sum(len(d["images"]) for d in all_data)
            total_answers = sum(d["answer_count"] for d in all_data)

            print(f"\n{'='*50}")
            print(f"🎉 완료!")
            print(f"{'='*50}")
            print(f"  게시글: {len(all_data)}건")
            print(f"  답변:   {total_answers}개")
            print(f"  이미지: {total_images}개")
            print(f"\n  📁 {os.path.abspath(OUTPUT_DIR)}/")
            print(f"    ├── inquiry_data.csv")
            print(f"    ├── inquiry_qa_pairs.jsonl")
            print(f"    ├── inquiry_full.json")
            print(f"    └── images/ ({total_images}개)")
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
