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
from services.comment_utils import get_comment_body_html


def _make_task_token(login: str, answers: list[bool]) -> str:
    """テスト正解ラベルを HMAC-SHA256 で署名したトークンを生成する。"""
    payload = json.dumps({"login": login, "answers": answers}, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload).decode()
    sig = hmac.new(QUIZ_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_task_token(token: str, login: str) -> list[bool] | None:
    """トークンを検証し、正解ラベルリストを返す。不正なら None。"""
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected_sig = hmac.new(QUIZ_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("login") != login:
            return None
        return [bool(a) for a in payload["answers"]]
    except Exception:
        return None


class _TaskAnswer(BaseModel):
    id: int
    prediction: bool


class _TaskSubmitRequest(BaseModel):
    task_token: str
    answers: list[_TaskAnswer]

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
    train_count: int = Query(40, ge=10, le=1000),
    test_count: int = Query(20, ge=5, le=500),
):
    """コーディングタスク用：ラベルあり学習データ＋ブラインドテストデータを返す。

    training: is_target ラベル付きコメント（学習用）
    test: ラベルなしコメント（予測対象）
    task_token: /quiz/task/submit に渡すことで採点できる署名済みトークン
    """
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

        uid = user_row["user_id"]
        target_need = train_count // 2 + test_count // 2
        other_need = (train_count - train_count // 2) + (test_count - test_count // 2)

        target_rows = comment_repo.fetch_quiz_target_comments(db, uid, target_need)
        other_rows = comment_repo.fetch_quiz_other_comments(db, uid, other_need)

    # DB データ不足時でも常に 1:1 クラス比を保つため、少ない方に合わせてから分割する
    # 例: target=750件・other=438件 → 両方 438 件に切り詰め、train:test 比率は維持
    n = min(len(target_rows), len(other_rows))
    if n == 0:
        return JSONResponse({"error": "insufficient_data"}, status_code=404)
    target_rows = target_rows[:n]
    other_rows = other_rows[:n]

    # train/test の要求比率を維持しながら n 件を分配
    # train_per_class = n * train_count / (train_count + test_count) を丸め
    train_per_class = min(train_count // 2, round(n * train_count / (train_count + test_count)))
    test_per_class = n - train_per_class

    train_target = target_rows[:train_per_class]
    test_target = target_rows[train_per_class : train_per_class + test_per_class]
    train_other = other_rows[:train_per_class]
    test_other = other_rows[train_per_class : train_per_class + test_per_class]

    training = [{"body": r["body"], "is_target": True} for r in train_target]
    training += [{"body": r["body"], "is_target": False} for r in train_other]
    random.shuffle(training)

    test_with_labels = [{"body": r["body"], "is_target": True} for r in test_target]
    test_with_labels += [{"body": r["body"], "is_target": False} for r in test_other]
    random.shuffle(test_with_labels)

    test_answers = [item["is_target"] for item in test_with_labels]
    test = [{"id": i, "body": item["body"]} for i, item in enumerate(test_with_labels)]

    return {
        "task_token": _make_task_token(login, test_answers),
        "target_login": login,
        "train_count": len(training),
        "test_count": len(test),
        "training": training,
        "test": test,
    }


@router.post("/api/u/{login}/quiz/task/submit")
def quiz_task_submit_api(login: str, body: _TaskSubmitRequest):
    """予測結果を採点して正答率を返す。

    task_token: /quiz/task から取得したトークン
    answers: [{id: int, prediction: bool}, ...] — test の各 id に対する予測
    """
    true_answers = _verify_task_token(body.task_token, login)
    if true_answers is None:
        return JSONResponse({"error": "invalid_token"}, status_code=400)

    pred_map = {a.id: a.prediction for a in body.answers}

    details = []
    correct = 0
    for i, actual in enumerate(true_answers):
        if i not in pred_map:
            return JSONResponse({"error": f"missing_answer_for_id_{i}"}, status_code=400)
        prediction = pred_map[i]
        is_correct = prediction == actual
        if is_correct:
            correct += 1
        details.append({"id": i, "prediction": prediction, "actual": actual, "correct": is_correct})

    total = len(true_answers)
    return {
        "accuracy": correct / total if total > 0 else 0.0,
        "correct": correct,
        "total": total,
        "details": details,
    }
