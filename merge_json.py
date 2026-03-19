"""
inquiry_all.json + inquiry_new.json → inquiry_all.json (갱신)
inquiry_comment_all.json + inquiry_comment_new.json → inquiry_comment_all.json (갱신)

- 날짜 정규화: T 제거 → 'YYYY-MM-DD HH:MM:SS' 형식
- inquiry_new의 ID는 inquiry_all.max_id + 1부터 재부여
- comment_new의 inquiry_id도 새 ID로 매핑, comment ID도 재부여
- 날짜 오름차순 정렬
- 머지 후 _new 파일 삭제
"""

import json
import os
import re
from datetime import datetime

INQ_ALL = "inquiry_all.json"
INQ_NEW = "inquiry_new.json"
CMT_ALL = "inquiry_comment_all.json"
CMT_NEW = "inquiry_comment_new.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fix_dt(s: str) -> str:
    """ISO 8601 → 'YYYY-MM-DD HH:MM:SS'"""
    if not s:
        return s
    s = re.sub(r'T', ' ', s)
    s = re.sub(r'\.\d+', '', s)
    s = re.sub(r'[Zz]$', '', s)
    s = re.sub(r'[+-]\d{2}:\d{2}$', '', s)
    return s.strip()


def parse_dt(s: str) -> datetime:
    s = fix_dt(s or '')
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return datetime.min


def normalize(d: dict) -> dict:
    """create_dt / update_dt T 제거"""
    if d.get("create_dt"):
        d["create_dt"] = fix_dt(d["create_dt"])
    if d.get("update_dt"):
        d["update_dt"] = fix_dt(d["update_dt"])
    return d


def merge():
    if not os.path.exists(INQ_NEW):
        print(f"⚠️  {INQ_NEW} 없음. 머지할 새 데이터가 없습니다.")
        return

    inq_all = list(map(normalize, load(INQ_ALL)))
    inq_new = list(map(normalize, load(INQ_NEW)))
    cmt_all = list(map(normalize, load(CMT_ALL)))
    cmt_new = list(map(normalize, load(CMT_NEW))) if os.path.exists(CMT_NEW) else []

    # ── 1. inquiry 병합 ──────────────────────────────
    max_inq_id = max(d["id"] for d in inq_all)

    id_map = {}
    new_id_counter = max_inq_id + 1
    for d in inq_new:
        id_map[d["id"]] = new_id_counter
        d["id"] = new_id_counter
        new_id_counter += 1

    combined_inq = inq_all + inq_new
    combined_inq.sort(key=lambda d: parse_dt(d["create_dt"]))

    # ── 2. comment 병합 ──────────────────────────────
    max_cmt_id = max(d["id"] for d in cmt_all)

    cmt_id_counter = max_cmt_id + 1
    for c in cmt_new:
        c["id"] = cmt_id_counter
        cmt_id_counter += 1
        old_inq_id = c.get("inquiry_id")
        if old_inq_id in id_map:
            c["inquiry_id"] = id_map[old_inq_id]

    combined_cmt = cmt_all + cmt_new
    combined_cmt.sort(key=lambda c: parse_dt(c["create_dt"]))

    # ── 3. 저장 ──────────────────────────────────────
    with open(INQ_ALL, "w", encoding="utf-8") as f:
        json.dump(combined_inq, f, ensure_ascii=False, indent=2)
    print(f"✅ {INQ_ALL}: {len(inq_all)}건 + {len(inq_new)}건 → 총 {len(combined_inq)}건")

    with open(CMT_ALL, "w", encoding="utf-8") as f:
        json.dump(combined_cmt, f, ensure_ascii=False, indent=2)
    print(f"✅ {CMT_ALL}: {len(cmt_all)}건 + {len(cmt_new)}건 → 총 {len(combined_cmt)}건")

    # ── 4. _new 파일 삭제 ─────────────────────────────
    os.remove(INQ_NEW)
    if os.path.exists(CMT_NEW):
        os.remove(CMT_NEW)
    print("🗑️  inquiry_new.json / inquiry_comment_new.json 삭제 완료")


if __name__ == "__main__":
    merge()
