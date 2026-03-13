"""stats ページの業務ロジック。
stats.py ルーターから統計計算を抽出したもの。
"""
from collections import defaultdict

from scipy.stats import mannwhitneyu

from repositories import stats_repo


def _calc_impact(active: list[float], inactive: list[float]) -> tuple[float, float, float, float]:
    """平均、変化率、Mann-Whitney U 検定の p 値を計算する。"""
    avg_a = round(sum(active) / len(active), 2)
    avg_i = round(sum(inactive) / len(inactive), 2)
    change = round((avg_a - avg_i) / avg_i * 100, 1) if avg_i > 0 else 0.0
    _, p = mannwhitneyu(active, inactive, alternative="two-sided")
    return avg_a, avg_i, change, round(p, 4)


def build_hourly_stats(db, uid: int) -> list[int]:
    """0〜23時の時間帯別コメント数（インデックス=時間）。"""
    rows = stats_repo.fetch_hourly_activity(db, uid)
    stats = [0] * 24
    for row in rows:
        hour = row["hour"]
        if 0 <= hour < 24:
            stats[hour] = row["count"]
    return stats


def build_weekday_stats(db, uid: int) -> list[int]:
    """0=日〜6=土の曜日別コメント数。"""
    rows = stats_repo.fetch_weekday_activity(db, uid)
    weekday_stats = [0] * 7
    for row in rows:
        wd = row["weekday"] - 1  # DAYOFWEEK: 1=Sun → 0
        if 0 <= wd < 7:
            weekday_stats[wd] = row["count"]
    return weekday_stats


def build_owners_stats(db, uid: int, total_comments: int) -> list[dict]:
    """配信者ごとのコメント数・比率・活動率を返す。"""
    owner_rows = stats_repo.fetch_owner_comment_counts(db, uid)
    activity_rows = stats_repo.fetch_owner_activity(db, uid)
    owner_activity_map = {int(row["owner_user_id"]): row for row in activity_rows}

    owners_stats = []
    for idx, row in enumerate(owner_rows, start=1):
        owner_id = int(row["owner_user_id"])
        count = int(row["count"] or 0)
        ratio = round((count / total_comments) * 100, 1) if total_comments > 0 else 0.0
        activity_row = owner_activity_map.get(owner_id)
        active_rate = None
        inactive_rate = None
        if activity_row:
            total_buckets = int(activity_row["total_buckets"] or 0)
            active_buckets = int(activity_row["active_buckets"] or 0)
            if total_buckets > 0:
                active_rate = round((active_buckets / total_buckets) * 100, 1)
                inactive_rate = round(100.0 - active_rate, 1)
        owners_stats.append({
            "rank": idx,
            "login": row["login"],
            "display_name": row["display_name"],
            "count": count,
            "ratio": ratio,
            "active_rate": active_rate,
            "inactive_rate": inactive_rate,
        })
    return owners_stats


def build_cn_scores(db, uid: int) -> dict | None:
    """コミュニティノート平均スコアと危険度分布。ノートがなければ None。"""
    cn_avg = stats_repo.fetch_cn_scores(db, uid)
    if cn_avg is None:
        return None

    avg_harm = float(cn_avg["avg_harm_risk"] or 0)
    avg_exag = float(cn_avg["avg_exaggeration"] or 0)
    avg_evid = float(cn_avg["avg_evidence_gap"] or 0)
    avg_subj = float(cn_avg["avg_subjectivity"] or 0)
    avg_danger = round((avg_harm + avg_exag + avg_evid + avg_subj) / 4, 1)

    danger_dist_rows = stats_repo.fetch_cn_danger_distribution(db, uid)
    danger_dist = [0] * 10
    for row in danger_dist_rows:
        idx = int(row["bucket"]) // 10
        if 0 <= idx < 10:
            danger_dist[idx] = row["cnt"]

    return {
        "avg_verifiability": round(float(cn_avg["avg_verifiability"] or 0), 1),
        "avg_harm_risk": round(avg_harm, 1),
        "avg_exaggeration": round(avg_exag, 1),
        "avg_evidence_gap": round(avg_evid, 1),
        "avg_subjectivity": round(avg_subj, 1),
        "avg_danger": avg_danger,
        "note_count": cn_avg["note_count"],
        "danger_dist": danger_dist,
    }


def build_impact_stats(db, uid: int) -> tuple[list[dict], dict | None]:
    """コメント影響度分析。VOD 数が多すぎる場合は空を返す。
    Returns (impact_stats, impact_total)
    """
    vod_count = stats_repo.count_user_vods(db, uid)
    if vod_count > 500:
        return [], None

    bucket_rows = stats_repo.fetch_impact_buckets(db, uid)

    owner_buckets: dict = defaultdict(lambda: {
        "login": "", "display_name": "",
        "active_comments": [], "inactive_comments": [],
        "active_unique": [], "inactive_unique": [],
    })
    all_active_comments: list[float] = []
    all_inactive_comments: list[float] = []
    all_active_unique: list[float] = []
    all_inactive_unique: list[float] = []

    for row in bucket_rows:
        oid = row["owner_user_id"]
        d = owner_buckets[oid]
        d["login"] = row["owner_login"]
        d["display_name"] = row["owner_display_name"] or row["owner_login"]
        oc = float(row["other_comments"])
        ou = float(row["other_unique"])
        if row["target_active"]:
            d["active_comments"].append(oc)
            d["active_unique"].append(ou)
            all_active_comments.append(oc)
            all_active_unique.append(ou)
        else:
            d["inactive_comments"].append(oc)
            d["inactive_unique"].append(ou)
            all_inactive_comments.append(oc)
            all_inactive_unique.append(ou)

    impact_stats = []
    for oid, d in sorted(owner_buckets.items(), key=lambda x: len(x[1]["active_comments"]), reverse=True):
        if len(d["active_comments"]) < 3 or len(d["inactive_comments"]) < 3:
            continue
        avg_a, avg_i, c_change, c_p = _calc_impact(d["active_comments"], d["inactive_comments"])
        avg_ua, avg_ui, u_change, u_p = _calc_impact(d["active_unique"], d["inactive_unique"])
        impact_stats.append({
            "owner_login": d["login"],
            "owner_display_name": d["display_name"],
            "active_buckets": len(d["active_comments"]),
            "inactive_buckets": len(d["inactive_comments"]),
            "avg_others_active": avg_a,
            "avg_others_inactive": avg_i,
            "comment_change": c_change,
            "p_value": c_p,
            "avg_unique_active": avg_ua,
            "avg_unique_inactive": avg_ui,
            "unique_change": u_change,
            "p_value_unique": u_p,
        })

    impact_total = None
    if len(all_active_comments) >= 3 and len(all_inactive_comments) >= 3:
        avg_a, avg_i, c_change, c_p = _calc_impact(all_active_comments, all_inactive_comments)
        avg_ua, avg_ui, u_change, u_p = _calc_impact(all_active_unique, all_inactive_unique)
        impact_total = {
            "active_buckets": len(all_active_comments),
            "inactive_buckets": len(all_inactive_comments),
            "avg_others_active": avg_a,
            "avg_others_inactive": avg_i,
            "comment_change": c_change,
            "p_value": c_p,
            "avg_unique_active": avg_ua,
            "avg_unique_inactive": avg_ui,
            "unique_change": u_change,
            "p_value_unique": u_p,
        }

    return impact_stats, impact_total
