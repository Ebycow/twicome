"""投票（いいね・dislike）のデータアクセス層。"""
from sqlalchemy import text


def increment_like(db, comment_id: str, count: int) -> bool:
    result = db.execute(
        text("UPDATE comments SET twicome_likes_count = twicome_likes_count + :count WHERE comment_id = :cid"),
        {"cid": comment_id, "count": count},
    )
    db.commit()
    return result.rowcount > 0


def increment_dislike(db, comment_id: str, count: int) -> bool:
    result = db.execute(
        text("UPDATE comments SET twicome_dislikes_count = twicome_dislikes_count + :count WHERE comment_id = :cid"),
        {"cid": comment_id, "count": count},
    )
    db.commit()
    return result.rowcount > 0
