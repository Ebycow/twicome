import base64
import hashlib
import hmac
import json
import random

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from core.config import DEFAULT_PLATFORM, QUIZ_SECRET_KEY
from core.db import SessionLocal
from core.templates import templates
from repositories import comment_repo, user_repo

# ---------------------------------------------------------------------------
# タスク設定定数
# ---------------------------------------------------------------------------

_TRAIN_PER_USER = 1000  # 各ユーザーから取得する学習コメント数
_TEST_PER_USER = 500  # テスト問題数（= 各ユーザーのテスト用コメント数）
_OTHER_USER_COUNT = 99  # 別人ユーザー数
_MIN_COMMENTS_REQUIRED = _TRAIN_PER_USER + _TEST_PER_USER  # 1100
_CANDIDATES_PER_QUESTION = _OTHER_USER_COUNT + 1  # 100


# ---------------------------------------------------------------------------
# トークン
# ---------------------------------------------------------------------------


def _make_task_token(login: str, correct_candidate_ids: list[int]) -> str:
    """テスト正解候補 ID リストを HMAC-SHA256 で署名したトークンを生成する。"""
    payload = json.dumps({"login": login, "answers": correct_candidate_ids}, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload).decode()
    sig = hmac.new(QUIZ_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_task_token(token: str, login: str) -> list[int] | None:
    """トークンを検証し、正解候補 ID リストを返す。不正なら None。"""
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected_sig = hmac.new(QUIZ_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("login") != login:
            return None
        return [int(a) for a in payload["answers"]]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# リクエストモデル
# ---------------------------------------------------------------------------


class _RankedAnswer(BaseModel):
    id: int
    ranked_candidates: list[int]  # candidate_id を予測確信度降順に並べた全候補リスト


class _TaskSubmitRequest(BaseModel):
    task_token: str
    answers: list[_RankedAnswer]


# ---------------------------------------------------------------------------
# ルーター
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/u/{login}/quiz", response_class=HTMLResponse)
def quiz_page(
    request: Request,
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return templates.TemplateResponse(
                "quiz.html",
                {
                    "request": request,
                    "error": "ユーザが見つかりませんでした",
                    "user": None,
                    "comment_count": 0,
                    "platform": platform,
                },
                status_code=404,
            )
        comment_count = comment_repo.count_comments(db, user_row["user_id"])

    return templates.TemplateResponse(
        "quiz.html",
        {
            "request": request,
            "error": None,
            "user": user_row,
            "comment_count": comment_count,
            "platform": platform,
        },
    )


@router.get("/api/u/{login}/quiz/start")
def quiz_start_api(
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
    count: int = Query(30, ge=10, le=100),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

        uid = user_row["user_id"]
        target_count = count // 2
        other_count = count - target_count

        target_comments = comment_repo.fetch_quiz_target_comments(db, uid, target_count)
        other_comments = comment_repo.fetch_quiz_other_comments(db, uid, other_count)

        from services.comment_utils import get_comment_body_html

        questions = []
        for r in target_comments:
            questions.append(
                {
                    "body": r["body"],
                    "body_html": get_comment_body_html(r),
                    "is_target": True,
                    "actual_commenter_display_name": r["commenter_display_name_snapshot"]
                    or r["commenter_login_snapshot"],
                    "vod_title": r["vod_title"],
                    "user_color": r["user_color"],
                }
            )
        for r in other_comments:
            questions.append(
                {
                    "body": r["body"],
                    "body_html": get_comment_body_html(r),
                    "is_target": False,
                    "actual_commenter_display_name": r["commenter_display_name_snapshot"]
                    or r["commenter_login_snapshot"],
                    "vod_title": r["vod_title"],
                    "user_color": r["user_color"],
                }
            )

        random.shuffle(questions)

    return {
        "user": user_row,
        "total": len(questions),
        "questions": questions,
    }


@router.get("/api/u/{login}/quiz/task")
def quiz_task_api(
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
):
    """コーディングタスク用：ランキング形式の識別チャレンジ。

    学習データ: 本人 _TRAIN_PER_USER 件 + 別人 _OTHER_USER_COUNT 人 × _TRAIN_PER_USER 件
    テスト: _TEST_PER_USER 問。各問は _CANDIDATES_PER_QUESTION 候補（本人 1 + 別人 99）。
    評価: Top-1 accuracy と MRR（Mean Reciprocal Rank）。

    学習データの user_idx フィールド:
        0 = ターゲット本人、1〜99 = 各別人（タスク内で一貫）
    """
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

        uid = user_row["user_id"]

        # ターゲットユーザーの件数チェック
        target_total = comment_repo.count_user_comments(db, uid)
        if target_total < _MIN_COMMENTS_REQUIRED:
            return JSONResponse(
                {
                    "error": "insufficient_target_comments",
                    "required": _MIN_COMMENTS_REQUIRED,
                    "actual": target_total,
                },
                status_code=400,
            )

        # 別人ユーザー選出
        other_user_ids = comment_repo.fetch_eligible_other_user_ids(
            db, uid, min_comments=_MIN_COMMENTS_REQUIRED, count=_OTHER_USER_COUNT
        )
        if len(other_user_ids) < _OTHER_USER_COUNT:
            return JSONResponse(
                {
                    "error": "insufficient_other_users",
                    "required": _OTHER_USER_COUNT,
                    "actual": len(other_user_ids),
                },
                status_code=400,
            )

        # 全ユーザーの最新 _MIN_COMMENTS_REQUIRED 件を取得（最新順、重複なし）
        all_user_ids = [uid, *other_user_ids]
        user_comments = comment_repo.fetch_recent_comments_by_users(
            db, all_user_ids, limit_per_user=_MIN_COMMENTS_REQUIRED
        )
        target_comments = user_comments.get(uid, [])

    # 学習データ: 各ユーザーの先頭 _TRAIN_PER_USER 件（= より最新の投稿）
    # user_idx=0 がターゲット本人、user_idx=1..99 が各別人
    training = [{"body": body, "is_target": True, "user_idx": 0} for body in target_comments[:_TRAIN_PER_USER]]
    for u_idx, other_uid in enumerate(other_user_ids, start=1):
        training += [
            {"body": body, "is_target": False, "user_idx": u_idx}
            for body in user_comments.get(other_uid, [])[:_TRAIN_PER_USER]
        ]
    random.shuffle(training)

    # テスト: 各ユーザーの _TRAIN_PER_USER+1 〜 _TRAIN_PER_USER+_TEST_PER_USER 件目
    test_target = target_comments[_TRAIN_PER_USER : _TRAIN_PER_USER + _TEST_PER_USER]
    test_others = {
        other_uid: user_comments.get(other_uid, [])[_TRAIN_PER_USER : _TRAIN_PER_USER + _TEST_PER_USER]
        for other_uid in other_user_ids
    }

    test = []
    correct_candidate_ids = []
    for q_id in range(_TEST_PER_USER):
        # 候補リスト: 本人 1 件 + 各別人 1 件をシャッフル
        raw = [{"body": test_target[q_id], "is_target": True}]
        for other_uid in other_user_ids:
            raw.append({"body": test_others[other_uid][q_id], "is_target": False})
        random.shuffle(raw)

        correct_cid = next(i for i, c in enumerate(raw) if c["is_target"])
        correct_candidate_ids.append(correct_cid)

        test.append(
            {
                "id": q_id,
                "candidates": [{"candidate_id": i, "body": c["body"]} for i, c in enumerate(raw)],
            }
        )

    return {
        "task_token": _make_task_token(login, correct_candidate_ids),
        "target_login": login,
        "train_count": len(training),
        "test_count": len(test),
        "candidates_per_question": _CANDIDATES_PER_QUESTION,
        "training": training,
        "test": test,
    }


@router.post("/api/u/{login}/quiz/task/submit")
def quiz_task_submit_api(login: str, body: _TaskSubmitRequest):
    """予測ランキングを採点して Top-1 accuracy と MRR を返す。

    answers[].ranked_candidates: candidate_id を予測確信度降順に並べた全 _CANDIDATES_PER_QUESTION 件のリスト。
    評価指標:
        top1_accuracy: 1 位が正解の割合
        mrr: 正解の順位の逆数の平均 (Mean Reciprocal Rank)
    """
    true_answers = _verify_task_token(body.task_token, login)
    if true_answers is None:
        return JSONResponse({"error": "invalid_token"}, status_code=400)

    pred_map = {a.id: a.ranked_candidates for a in body.answers}

    reciprocal_ranks = []
    correct_top1 = 0

    for i, correct_cid in enumerate(true_answers):
        if i not in pred_map:
            return JSONResponse({"error": f"missing_answer_for_id_{i}"}, status_code=400)
        ranking = pred_map[i]
        if len(ranking) != _CANDIDATES_PER_QUESTION:
            return JSONResponse(
                {
                    "error": f"wrong_ranking_length_for_id_{i}",
                    "expected": _CANDIDATES_PER_QUESTION,
                    "actual": len(ranking),
                },
                status_code=400,
            )
        if set(ranking) != set(range(_CANDIDATES_PER_QUESTION)):
            return JSONResponse({"error": f"invalid_candidate_ids_for_id_{i}"}, status_code=400)

        rank = ranking.index(correct_cid) + 1  # 1始まり
        reciprocal_ranks.append(1.0 / rank)
        if rank == 1:
            correct_top1 += 1

    total = len(true_answers)
    mrr = sum(reciprocal_ranks) / total if total > 0 else 0.0
    top1 = correct_top1 / total if total > 0 else 0.0

    return {
        "top1_accuracy": round(top1, 4),
        "mrr": round(mrr, 4),
        "correct_top1": correct_top1,
        "total": total,
    }
