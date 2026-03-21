"""
統合テスト用シードデータヘルパー。
各テストが必要なデータを DB に投入するための関数群。
"""

from datetime import UTC, datetime


def seed_user(
    db, *, user_id=1, login="testuser", display_name="テストユーザー", platform="twitch", profile_image_url=None
) -> dict:
    from sqlalchemy import text

    db.execute(
        text("""
            INSERT INTO users (user_id, login, display_name, profile_image_url, platform, created_at, updated_at)
            VALUES (:user_id, :login, :display_name, :profile_image_url, :platform, NOW(6), NOW(6))
            ON DUPLICATE KEY UPDATE
                user_id=VALUES(user_id),
                login=VALUES(login),
                display_name=VALUES(display_name),
                profile_image_url=VALUES(profile_image_url),
                platform=VALUES(platform),
                updated_at=VALUES(updated_at)
        """),
        {
            "user_id": user_id,
            "login": login,
            "display_name": display_name,
            "profile_image_url": profile_image_url,
            "platform": platform,
        },
    )
    db.commit()
    return {"user_id": user_id, "login": login, "display_name": display_name, "platform": platform}


def seed_vod(
    db,
    *,
    vod_id=100,
    owner_user_id=1,
    title="テスト配信",
    url="https://www.twitch.tv/videos/100",
    youtube_url=None,
    length_seconds=3600,
) -> dict:
    from sqlalchemy import text

    db.execute(
        text("""
            INSERT INTO vods (vod_id, owner_user_id, title, url, youtube_url, length_seconds, created_at_utc)
            VALUES (:vod_id, :owner_user_id, :title, :url, :youtube_url, :length_seconds, NOW(6))
            ON DUPLICATE KEY UPDATE
                owner_user_id=VALUES(owner_user_id),
                title=VALUES(title),
                url=VALUES(url),
                youtube_url=VALUES(youtube_url),
                length_seconds=VALUES(length_seconds)
        """),
        {
            "vod_id": vod_id,
            "owner_user_id": owner_user_id,
            "title": title,
            "url": url,
            "youtube_url": youtube_url,
            "length_seconds": length_seconds,
        },
    )
    db.commit()
    return {"vod_id": vod_id, "owner_user_id": owner_user_id, "title": title}


def seed_comment(
    db,
    *,
    comment_id="c001",
    vod_id=100,
    commenter_user_id=1,
    commenter_login_snapshot="testuser",
    body="テストコメント",
    offset_seconds=60,
    created_at: datetime | None = None,
    likes=0,
    dislikes=0,
) -> dict:
    from sqlalchemy import text

    if created_at is None:
        created_at = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    naive_utc = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
    db.execute(
        text("""
            INSERT INTO comments (
                comment_id, vod_id, commenter_user_id, commenter_login_snapshot,
                body, offset_seconds, comment_created_at_utc,
                twicome_likes_count, twicome_dislikes_count
            ) VALUES (
                :comment_id, :vod_id, :commenter_user_id, :commenter_login_snapshot,
                :body, :offset_seconds, :created_at,
                :likes, :dislikes
            )
            ON DUPLICATE KEY UPDATE
                vod_id=VALUES(vod_id),
                commenter_user_id=VALUES(commenter_user_id),
                commenter_login_snapshot=VALUES(commenter_login_snapshot),
                body=VALUES(body),
                offset_seconds=VALUES(offset_seconds),
                comment_created_at_utc=VALUES(comment_created_at_utc),
                twicome_likes_count=VALUES(twicome_likes_count),
                twicome_dislikes_count=VALUES(twicome_dislikes_count)
        """),
        {
            "comment_id": comment_id,
            "vod_id": vod_id,
            "commenter_user_id": commenter_user_id,
            "commenter_login_snapshot": commenter_login_snapshot,
            "body": body,
            "offset_seconds": offset_seconds,
            "created_at": naive_utc,
            "likes": likes,
            "dislikes": dislikes,
        },
    )
    db.commit()
    return {"comment_id": comment_id, "vod_id": vod_id, "body": body}
