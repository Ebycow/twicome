import services.stats_service as stats_service


class TestCalcImpact:
    def test_calculates_change_and_p_value(self, monkeypatch):
        monkeypatch.setattr(stats_service, "mannwhitneyu", lambda *_args, **_kwargs: (0.0, 0.12345))

        result = stats_service._calc_impact([10, 20, 30], [5, 10, 15])

        assert result == (20.0, 10.0, 100.0, 0.1235)

    def test_returns_zero_change_when_inactive_average_is_zero(self, monkeypatch):
        monkeypatch.setattr(stats_service, "mannwhitneyu", lambda *_args, **_kwargs: (0.0, 0.5))

        result = stats_service._calc_impact([0, 0, 0], [0, 0, 0])

        assert result == (0.0, 0.0, 0.0, 0.5)


class TestBuildHourlyStats:
    def test_places_counts_in_valid_hour_slots_only(self, monkeypatch):
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_hourly_activity",
            lambda _db, _uid: [
                {"hour": 0, "count": 2},
                {"hour": 23, "count": 7},
                {"hour": 24, "count": 99},
            ],
        )

        result = stats_service.build_hourly_stats(object(), 1)

        assert result[0] == 2
        assert result[23] == 7
        assert len(result) == 24


class TestBuildWeekdayStats:
    def test_places_counts_in_valid_weekday_slots_only(self, monkeypatch):
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_weekday_activity",
            lambda _db, _uid: [
                {"weekday": 1, "count": 3},
                {"weekday": 7, "count": 4},
                {"weekday": 9, "count": 99},
            ],
        )

        result = stats_service.build_weekday_stats(object(), 1)

        assert result[0] == 3
        assert result[6] == 4
        assert len(result) == 7


class TestBuildOwnersStats:
    def test_builds_ratios_and_activity_rates(self, monkeypatch):
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_owner_comment_counts",
            lambda _db, _uid: [
                {"owner_user_id": 10, "login": "streamer_a", "display_name": "Streamer A", "count": 6},
                {"owner_user_id": 11, "login": "streamer_b", "display_name": "Streamer B", "count": 4},
            ],
        )
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_owner_activity",
            lambda _db, _uid: [
                {"owner_user_id": 10, "total_buckets": 10, "active_buckets": 4},
                {"owner_user_id": 11, "total_buckets": 0, "active_buckets": 0},
            ],
        )

        result = stats_service.build_owners_stats(object(), 1, total_comments=10)

        assert result == [
            {
                "rank": 1,
                "login": "streamer_a",
                "display_name": "Streamer A",
                "count": 6,
                "ratio": 60.0,
                "active_rate": 40.0,
                "inactive_rate": 60.0,
            },
            {
                "rank": 2,
                "login": "streamer_b",
                "display_name": "Streamer B",
                "count": 4,
                "ratio": 40.0,
                "active_rate": None,
                "inactive_rate": None,
            },
        ]

    def test_total_comments_zero_produces_zero_ratio(self, monkeypatch):
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_owner_comment_counts",
            lambda _db, _uid: [{"owner_user_id": 10, "login": "streamer", "display_name": None, "count": 1}],
        )
        monkeypatch.setattr(stats_service.stats_repo, "fetch_owner_activity", lambda _db, _uid: [])

        result = stats_service.build_owners_stats(object(), 1, total_comments=0)

        assert result[0]["ratio"] == 0.0


class TestBuildCnScores:
    def test_returns_none_when_no_notes_exist(self, monkeypatch):
        monkeypatch.setattr(stats_service.stats_repo, "fetch_cn_scores", lambda _db, _uid: None)

        assert stats_service.build_cn_scores(object(), 1) is None

    def test_builds_score_summary_and_histogram(self, monkeypatch):
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_cn_scores",
            lambda _db, _uid: {
                "avg_verifiability": 70.4,
                "avg_harm_risk": 20.4,
                "avg_exaggeration": 30.4,
                "avg_evidence_gap": 40.4,
                "avg_subjectivity": 50.4,
                "note_count": 3,
            },
        )
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_cn_danger_distribution",
            lambda _db, _uid: [
                {"bucket": 0, "cnt": 1},
                {"bucket": 20, "cnt": 2},
                {"bucket": 90, "cnt": 3},
                {"bucket": 100, "cnt": 999},
            ],
        )

        result = stats_service.build_cn_scores(object(), 1)

        assert result == {
            "avg_verifiability": 70.4,
            "avg_harm_risk": 20.4,
            "avg_exaggeration": 30.4,
            "avg_evidence_gap": 40.4,
            "avg_subjectivity": 50.4,
            "avg_danger": 35.4,
            "note_count": 3,
            "danger_dist": [1, 0, 2, 0, 0, 0, 0, 0, 0, 3],
        }


class TestBuildImpactStats:
    def test_returns_empty_when_vod_count_too_large(self, monkeypatch):
        monkeypatch.setattr(stats_service.stats_repo, "count_user_vods", lambda _db, _uid: 501)

        assert stats_service.build_impact_stats(object(), 1) == ([], None)

    def test_builds_owner_and_total_stats_for_sufficient_buckets(self, monkeypatch):
        monkeypatch.setattr(stats_service.stats_repo, "count_user_vods", lambda _db, _uid: 10)
        monkeypatch.setattr(
            stats_service.stats_repo,
            "fetch_impact_buckets",
            lambda _db, _uid: [
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 10,
                    "other_unique": 5,
                    "target_active": 1,
                },
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 11,
                    "other_unique": 6,
                    "target_active": 1,
                },
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 12,
                    "other_unique": 7,
                    "target_active": 1,
                },
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 3,
                    "other_unique": 1,
                    "target_active": 0,
                },
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 4,
                    "other_unique": 2,
                    "target_active": 0,
                },
                {
                    "owner_user_id": 10,
                    "owner_login": "streamer_a",
                    "owner_display_name": "Streamer A",
                    "other_comments": 5,
                    "other_unique": 3,
                    "target_active": 0,
                },
                {
                    "owner_user_id": 20,
                    "owner_login": "streamer_b",
                    "owner_display_name": None,
                    "other_comments": 9,
                    "other_unique": 4,
                    "target_active": 1,
                },
                {
                    "owner_user_id": 20,
                    "owner_login": "streamer_b",
                    "owner_display_name": None,
                    "other_comments": 2,
                    "other_unique": 1,
                    "target_active": 0,
                },
            ],
        )
        monkeypatch.setattr(stats_service, "_calc_impact", lambda *_args: (9.9, 4.4, 125.0, 0.0123))

        impact_stats, impact_total = stats_service.build_impact_stats(object(), 1)

        assert impact_stats == [
            {
                "owner_login": "streamer_a",
                "owner_display_name": "Streamer A",
                "active_buckets": 3,
                "inactive_buckets": 3,
                "avg_others_active": 9.9,
                "avg_others_inactive": 4.4,
                "comment_change": 125.0,
                "p_value": 0.0123,
                "avg_unique_active": 9.9,
                "avg_unique_inactive": 4.4,
                "unique_change": 125.0,
                "p_value_unique": 0.0123,
            }
        ]
        assert impact_total == {
            "active_buckets": 4,
            "inactive_buckets": 4,
            "avg_others_active": 9.9,
            "avg_others_inactive": 4.4,
            "comment_change": 125.0,
            "p_value": 0.0123,
            "avg_unique_active": 9.9,
            "avg_unique_inactive": 4.4,
            "unique_change": 125.0,
            "p_value_unique": 0.0123,
        }
