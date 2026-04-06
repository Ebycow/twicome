"""stats ページ用のデータアクセス層。

stats.py ルーターから SQL を抽出したもの。
"""

from sqlalchemy import text


def count_user_comments(db, uid: int) -> int:
    """ユーザーの総コメント数を返す。"""
    row = (
        db.execute(
            text("SELECT COUNT(*) AS cnt FROM comments WHERE commenter_user_id = :uid"),
            {"uid": uid},
        )
        .mappings()
        .first()
    )
    return int(row["cnt"] or 0)


def fetch_hourly_activity(db, uid: int) -> list[dict]:
    """コメント時刻の時間帯別集計（JST）。"""
    rows = (
        db.execute(
            text("""
            SELECT HOUR(comment_created_at_utc + INTERVAL 9 HOUR) AS hour, COUNT(*) AS count
            FROM comments
            WHERE commenter_user_id = :uid AND comment_created_at_utc IS NOT NULL
            GROUP BY hour
            ORDER BY hour
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_hourly_by_weekday(db, uid: int) -> list[dict]:
    """コメント時刻の曜日×時間帯別集計（JST）。"""
    rows = (
        db.execute(
            text("""
            SELECT
                DAYOFWEEK(comment_created_at_utc + INTERVAL 9 HOUR) AS weekday,
                HOUR(comment_created_at_utc + INTERVAL 9 HOUR) AS hour,
                COUNT(*) AS count
            FROM comments
            WHERE commenter_user_id = :uid AND comment_created_at_utc IS NOT NULL
            GROUP BY weekday, hour
            ORDER BY weekday, hour
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_weekday_activity(db, uid: int) -> list[dict]:
    """コメント時刻の曜日別集計（JST）。"""
    rows = (
        db.execute(
            text("""
            SELECT DAYOFWEEK(comment_created_at_utc + INTERVAL 9 HOUR) AS weekday, COUNT(*) AS count
            FROM comments
            WHERE commenter_user_id = :uid AND comment_created_at_utc IS NOT NULL
            GROUP BY weekday
            ORDER BY weekday
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_owner_comment_counts(db, uid: int) -> list[dict]:
    """配信者ごとのコメント数集計。"""
    rows = (
        db.execute(
            text("""
            SELECT u.user_id AS owner_user_id, u.login, u.display_name, COUNT(*) AS count
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE c.commenter_user_id = :uid
            GROUP BY u.user_id, u.login, u.display_name
            ORDER BY count DESC
            LIMIT 50
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_owner_activity(db, uid: int) -> list[dict]:
    """配信者ごとの VOD バケット活動率（active_rate 計算用）。"""
    rows = (
        db.execute(
            text("""
            WITH target_vods AS (
                SELECT DISTINCT c.vod_id
                FROM comments c
                WHERE c.commenter_user_id = :uid
            ),
            vod_totals AS (
                SELECT
                    v.owner_user_id,
                    v.vod_id,
                    GREATEST(
                        COALESCE(CEIL(v.length_seconds / 300.0), 0),
                        COALESCE(CEIL((MAX(ca.offset_seconds) + 1) / 300.0), 0),
                        1
                    ) AS total_buckets
                FROM target_vods tv
                JOIN vods v ON v.vod_id = tv.vod_id
                LEFT JOIN comments ca ON ca.vod_id = tv.vod_id
                GROUP BY v.owner_user_id, v.vod_id, v.length_seconds
            ),
            owner_totals AS (
                SELECT owner_user_id, SUM(total_buckets) AS total_buckets
                FROM vod_totals
                GROUP BY owner_user_id
            ),
            owner_active AS (
                SELECT
                    v.owner_user_id,
                    COUNT(DISTINCT CONCAT(c.vod_id, ':', FLOOR(c.offset_seconds / 300))) AS active_buckets
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                WHERE c.commenter_user_id = :uid
                GROUP BY v.owner_user_id
            )
            SELECT
                ot.owner_user_id,
                ot.total_buckets,
                COALESCE(oa.active_buckets, 0) AS active_buckets
            FROM owner_totals ot
            LEFT JOIN owner_active oa ON oa.owner_user_id = ot.owner_user_id
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def count_user_vods(db, uid: int) -> int:
    """ユーザーがコメントした VOD の総数を返す。"""
    row = (
        db.execute(
            text("SELECT COUNT(DISTINCT vod_id) AS cnt FROM comments WHERE commenter_user_id = :uid"),
            {"uid": uid},
        )
        .mappings()
        .first()
    )
    return int(row["cnt"] or 0)


def fetch_impact_buckets(db, uid: int) -> list[dict]:
    """コメント影響度分析用のバケットデータ。"""
    rows = (
        db.execute(
            text("""
            WITH target_vods AS (
                SELECT DISTINCT vod_id FROM comments WHERE commenter_user_id = :uid
            )
            SELECT
                v.owner_user_id,
                u.login AS owner_login,
                u.display_name AS owner_display_name,
                c.vod_id,
                FLOOR(c.offset_seconds / 300) AS bucket,
                SUM(CASE WHEN c.commenter_user_id != :uid THEN 1 ELSE 0 END) AS other_comments,
                COUNT(DISTINCT CASE WHEN c.commenter_user_id != :uid THEN c.commenter_user_id END) AS other_unique,
                MAX(CASE WHEN c.commenter_user_id = :uid THEN 1 ELSE 0 END) AS target_active
            FROM comments c
            INNER JOIN target_vods tv ON tv.vod_id = c.vod_id
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            GROUP BY v.owner_user_id, u.login, u.display_name, c.vod_id, bucket
            HAVING other_comments > 0
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_broadcaster_last_comment(db, uid: int) -> list[dict]:
    """配信者ごとのユーザーの最終書き込み日時を返す。"""
    rows = (
        db.execute(
            text("""
            SELECT u.user_id AS owner_user_id, u.login, u.display_name,
                   MAX(c.comment_created_at_utc) AS last_comment_at
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE c.commenter_user_id = :uid AND c.comment_created_at_utc IS NOT NULL
            GROUP BY u.user_id, u.login, u.display_name
            ORDER BY last_comment_at DESC
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_monthly_activity(db, uid: int) -> list[dict]:
    """コメント時刻の月別集計（JST）。"""
    rows = (
        db.execute(
            text("""
            SELECT DATE_FORMAT(comment_created_at_utc + INTERVAL 9 HOUR, '%Y-%m') AS month,
                   COUNT(*) AS count
            FROM comments
            WHERE commenter_user_id = :uid AND comment_created_at_utc IS NOT NULL
            GROUP BY month
            ORDER BY month
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_cn_scores(db, uid: int) -> dict | None:
    """コミュニティノートの平均スコア。ノートがなければ None。"""
    row = (
        db.execute(
            text("""
            SELECT
                AVG(cn.verifiability) AS avg_verifiability,
                AVG(cn.harm_risk) AS avg_harm_risk,
                AVG(cn.exaggeration) AS avg_exaggeration,
                AVG(cn.evidence_gap) AS avg_evidence_gap,
                AVG(cn.subjectivity) AS avg_subjectivity,
                COUNT(*) AS note_count
            FROM community_notes cn
            JOIN comments c ON c.comment_id = cn.comment_id
            WHERE c.commenter_user_id = :uid
        """),
            {"uid": uid},
        )
        .mappings()
        .first()
    )
    if not row or not row["note_count"]:
        return None
    return dict(row)


def fetch_cn_danger_distribution(db, uid: int) -> list[dict]:
    """危険度スコアのヒストグラム（10刻み）。"""
    rows = (
        db.execute(
            text("""
            SELECT
                LEAST(FLOOR((cn.harm_risk + cn.exaggeration + cn.evidence_gap + cn.subjectivity) / 4 / 10) * 10,
                      90) AS bucket,
                COUNT(*) AS cnt
            FROM community_notes cn
            JOIN comments c ON c.comment_id = cn.comment_id
            WHERE c.commenter_user_id = :uid
            GROUP BY bucket
            ORDER BY bucket
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_cn_status_distribution(db, uid: int) -> dict:
    """コミュニティノートのステータス分布 {status: count}。"""
    rows = (
        db.execute(
            text("""
            SELECT cn.status, COUNT(*) AS cnt
            FROM community_notes cn
            JOIN comments c ON c.comment_id = cn.comment_id
            WHERE c.commenter_user_id = :uid
            GROUP BY cn.status
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return {row["status"]: row["cnt"] for row in rows}
