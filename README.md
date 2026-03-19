# ATL Scraper - 문의게시판 스크래퍼

SK AX AI Talent Lab 문의게시판에서 데이터를 수집하는 스크래퍼입니다.

---

## 파일 구성

```
atl_scrapper/
├── scrape_update.py              # 증분 수집 스크래퍼 (신규 게시글만)
├── merge_json.py                 # 신규 수집 데이터를 전체 데이터에 병합
├── make_test.py                  # 학습/테스트 데이터셋 분리 생성
├── .env                          # 로그인 계정 정보
│
├── inquiry_all.json              # 전체 문의 데이터 (날짜 오름차순)
├── inquiry_comment_all.json      # 전체 댓글 데이터 (날짜 오름차순)
│
├── inquiry_new.json              # 신규 수집 문의 ← scrape_update.py 실행 시 생성
├── inquiry_comment_new.json      # 신규 수집 댓글 ← scrape_update.py 실행 시 생성
│
├── inquiry_train.json            # 학습용 문의 (댓글 있는 것) ← make_test.py 실행 시 생성
├── inquiry_comment_train.json    # 학습용 댓글                ← make_test.py 실행 시 생성
└── inquiry_test.json             # 테스트용 문의 (댓글 없는 것) ← make_test.py 실행 시 생성
```

---

## 사전 준비

### 1. 패키지 설치

```bash
pip install selenium webdriver-manager python-dotenv
```

### 2. `.env` 파일 설정

```env
USERNAME=your_id@email.com
PASSWORD=your_password
```

### 3. Chrome 브라우저 설치

Chrome이 설치되어 있어야 합니다. ChromeDriver는 `webdriver-manager`가 자동으로 설치합니다.

---

## 사용 순서

### 신규 게시글 수집

```bash
# 1단계: 최신 게시글 수집 → inquiry_new.json 생성
python scrape_update.py

# 2단계: 전체 데이터에 병합 → inquiry_all.json 갱신, _new 파일 자동 삭제
python merge_json.py
```

### 학습/테스트 데이터셋 생성

```bash
# merge_json.py 실행 후 진행
python make_test.py
```

| 출력 파일 | 내용 |
|-----------|------|
| `inquiry_train.json` | 댓글이 달린 문의 (학습용) |
| `inquiry_comment_train.json` | 학습용 문의의 댓글 |
| `inquiry_test.json` | 댓글이 없는 문의 (테스트용) |

---

## 동작 방식

### `scrape_update.py`

1. `inquiry_all.json`에서 마지막 수집 날짜와 최대 ID를 읽음
2. 문의게시판 1페이지(최신)부터 순서대로 탐색
3. **공지 게시글** → 스킵
4. **이미지 포함 게시글** → 스킵
5. **이미 수집된 날짜 이하 게시글** 만나면 중단
6. 네트워크 API 응답에서 정확한 타임스탬프 및 댓글 내용 추출
7. `inquiry_new.json` / `inquiry_comment_new.json`에 저장

### `merge_json.py`

1. `inquiry_all.json` + `inquiry_new.json` 병합
2. 날짜 정규화: `T` 제거 → `YYYY-MM-DD HH:MM:SS` 형식
3. ID 재부여 (신규 데이터의 ID를 기존 최대 ID 이후로 재부여)
4. 댓글의 `inquiry_id`도 새 ID로 매핑
5. 날짜 오름차순 정렬 후 저장
6. `_new.json` 파일 자동 삭제

---

## 출력 파일 형식

### 문의 (`inquiry_all.json`)

```json
[
  {
    "id": 1,
    "title": "게시글 제목",
    "content": "<p>HTML 본문 내용</p>",
    "author_id": null,
    "author_name": "작성자명",
    "file_ids": "[]",
    "group_id": null,
    "status": "open",
    "is_pinned": 0,
    "create_dt": "2026-03-11 14:32:10",
    "update_dt": "2026-03-11 14:32:10"
  }
]
```

- `status`: `"open"` (답변 대기) / `"closed"` (답변 완료)
- `author_id`: UI에서 확인 불가하여 `null`로 저장
- `create_dt`: `YYYY-MM-DD HH:MM:SS` 형식 (API에서 정확한 시간 추출)

### 댓글 (`inquiry_comment_all.json`)

```json
[
  {
    "id": 1,
    "inquiry_id": 1,
    "content": "<p>HTML 댓글 내용</p>",
    "author_id": null,
    "author_name": "운영자명",
    "file_ids": null,
    "is_admin": 1,
    "create_dt": "2026-03-11 14:35:22",
    "update_dt": "2026-03-11 14:35:22"
  }
]
```

- `is_admin`: 운영자 댓글 `1` / 일반 사용자 댓글 `0`
- `inquiry_id`: 해당 문의의 `id`와 매핑
