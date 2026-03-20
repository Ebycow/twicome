"""投票（いいね・dislike）のデータアクセス層。"""

from sqlalchemy import text


def increment_like(db, comment_id: str, count: int) -> bool:
    """コメントのいいね数を count だけ増やす。更新行あれば True。"""
    result = db.execute(
        text("UPDATE comments SET twicome_likes_count = twicome_likes_count + :count WHERE comment_id = :cid"),
        {"cid": comment_id, "count": count},
    )
    return result.rowcount > 0


def increment_dislike(db, comment_id: str, count: int) -> bool:
    """コメントの dislike 数を count だけ増やす。更新行あれば True。"""
    result = db.execute(
        text("UPDATE comments SET twicome_dislikes_count = twicome_dislikes_count + :count WHERE comment_id = :cid"),
        {"cid": comment_id, "count": count},
    )
    return result.rowcount > 0
