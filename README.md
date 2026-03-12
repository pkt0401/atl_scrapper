# ATL Scraper - 문의게시판 스크래퍼

SK AX AI Talent Lab 문의게시판에서 데이터를 수집하는 스크래퍼입니다.

---

## 파일 구성

```
atl_scrapper/
├── scrape_march.py          # 메인 스크래퍼 (3월 이후 데이터 수집)
├── .env                     # 로그인 계정 정보 (아래 참고)
├── inquiry_all.json         # 기존 문의 데이터 (~ 2026-02-27)
├── inquiry_comment_all.json # 기존 댓글 데이터 (~ 2026-02-27)
├── inquiry_new.json         # 신규 수집 문의 데이터 (2026-03-01 ~) ← 실행 후 생성
└── inquiry_comment_new.json # 신규 수집 댓글 데이터 (2026-03-01 ~) ← 실행 후 생성
```

---

## 사전 준비

### 1. 패키지 설치

```bash
pip install selenium webdriver-manager beautifulsoup4 python-dotenv
```

### 2. `.env` 파일 설정

프로젝트 루트의 `.env` 파일에 로그인 계정을 입력합니다.

```env
USERNAME=your_id@email.com
PASSWORD=your_password
```

### 3. Chrome 브라우저 설치

Chrome이 설치되어 있어야 합니다. ChromeDriver는 `webdriver-manager`가 자동으로 설치합니다.

---

## 실행 방법

```bash
cd c:\atl_scrapper
python scrape_march.py
```

실행하면 Chrome 브라우저가 자동으로 열립니다.

- `.env`에 계정 정보가 있으면 **자동 로그인** 시도
- 자동 로그인 실패 시 브라우저에서 **직접 로그인** 후 터미널에서 Enter 입력

---

## 동작 방식

1. 문의게시판 1페이지(최신)부터 순서대로 탐색
2. 각 게시글의 날짜를 확인
3. **공지 게시글** → 날짜 무관하게 스킵
4. **이미지/첨부파일 포함 게시글** → 스킵
5. **2026-03-01 미만 게시글** 만나면 수집 중단
6. 수집된 데이터를 두 파일로 저장

---

## 출력 파일 형식

### `inquiry_new.json` (문의 게시글)

`inquiry_all.json`과 동일한 구조입니다.

```json
[
  {
    "id": 103,
    "title": "게시글 제목",
    "content": "<p>HTML 본문 내용</p>",
    "author_id": null,
    "author_name": "작성자명",
    "file_ids": "[]",
    "group_id": null,
    "status": "open",
    "is_pinned": 0,
    "create_dt": "2026-03-11 00:00:00",
    "update_dt": "2026-03-11 00:00:00"
  }
]
```

> `author_id`는 프론트엔드 UI에서 integer 값을 확인할 수 없어 `null`로 저장되며, 대신 `author_name` 필드에 텍스트로 저장됩니다.

### `inquiry_comment_new.json` (댓글)

`inquiry_comment_all.json`과 동일한 구조입니다.

```json
[
  {
    "id": 124,
    "inquiry_id": 103,
    "content": "<p>HTML 댓글 내용</p>",
    "author_id": null,
    "author_name": "운영자명",
    "file_ids": null,
    "is_admin": 1,
    "create_dt": "2026-03-11 00:00:00",
    "update_dt": "2026-03-11 00:00:00"
  }
]
```

> `is_admin`: 운영자 댓글이면 `1`, 일반 사용자 댓글이면 `0`

---

## 수집 범위 변경

수집 기준 날짜를 바꾸려면 [scrape_march.py](scrape_march.py) 상단 설정을 수정합니다.

```python
# scrape_march.py 30번째 줄
CUTOFF_DATE = datetime(2026, 3, 1)   # 이 날짜 이전 게시글은 수집 안 함
```

예시: 4월 이후만 수집하려면 `datetime(2026, 4, 1)`으로 변경

---

## ID 이어받기

`inquiry_new.json`의 ID는 기존 데이터의 마지막 ID 이후부터 시작합니다.

| 파일 | 기존 마지막 ID | 신규 시작 ID |
|------|--------------|------------|
| inquiry | 102 | 103 |
| comment | 123 | 124 |

기존 데이터가 업데이트되어 마지막 ID가 바뀐 경우, [scrape_march.py](scrape_march.py) 내 카운터를 수정합니다.

```python
# scrape_march.py 364-365번째 줄
inq_id = 103   # inquiry_all.json 마지막 id + 1
cmt_id = 124   # inquiry_comment_all.json 마지막 id + 1
```
