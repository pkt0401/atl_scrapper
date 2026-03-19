"""
댓글이 없는 문의 → 테스트용 파일
댓글이 있는 문의 → 학습용 파일

입력:
  inquiry_all.json
  inquiry_comment_all.json

출력:
  inquiry_test.json          ← 댓글 없는 문의 (테스트용)
  inquiry_train.json         ← 댓글 있는 문의 (학습용)
  inquiry_comment_train.json ← 학습용 문의의 댓글
"""

import json
import os

INQ_ALL        = "inquiry_all.json"
CMT_ALL        = "inquiry_comment_all.json"
INQ_TEST       = "inquiry_test.json"
INQ_TRAIN      = "inquiry_train.json"
CMT_TRAIN      = "inquiry_comment_train.json"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_test():
    inquiries = load(INQ_ALL)
    comments  = load(CMT_ALL)

    inq_ids_with_comments = {c["inquiry_id"] for c in comments}

    # 댓글 없는 문의 → 테스트용
    test_inq   = [d for d in inquiries if d["id"] not in inq_ids_with_comments]
    # 댓글 있는 문의 → 학습용
    train_inq  = [d for d in inquiries if d["id"] in inq_ids_with_comments]
    train_cmt  = [c for c in comments  if c["inquiry_id"] in inq_ids_with_comments]

    with open(INQ_TEST, "w", encoding="utf-8") as f:
        json.dump(test_inq, f, ensure_ascii=False, indent=2)
    print(f"[OK] {INQ_TEST}  (test)  : {len(test_inq)}건")

    with open(INQ_TRAIN, "w", encoding="utf-8") as f:
        json.dump(train_inq, f, ensure_ascii=False, indent=2)
    print(f"[OK] {INQ_TRAIN} (train) : {len(train_inq)}건")

    with open(CMT_TRAIN, "w", encoding="utf-8") as f:
        json.dump(train_cmt, f, ensure_ascii=False, indent=2)
    print(f"[OK] {CMT_TRAIN} (train) : {len(train_cmt)}건")


if __name__ == "__main__":
    make_test()
