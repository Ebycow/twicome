import pytest
import routers.clusters as clusters_router

from tests.integration.helpers import seed_comment, seed_user, seed_vod


@pytest.fixture()
def seeded_cluster_data(db):
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login="viewer", platform="twitch", display_name="ビューワー")
    seed_vod(db, vod_id=100, owner_user_id=1, title="クラスタ配信")
    seed_comment(
        db,
        comment_id="c1",
        vod_id=100,
        commenter_user_id=2,
        commenter_login_snapshot="viewer",
        body="クラスタコメント1",
    )
    seed_comment(
        db,
        comment_id="c2",
        vod_id=100,
        commenter_user_id=2,
        commenter_login_snapshot="viewer",
        body="クラスタコメント2",
    )


class TestBuildClusterDisplay:
    def test_returns_empty_for_empty_clusters(self, db):
        assert clusters_router._build_cluster_display([], db) == []

    def test_maps_representative_ids_to_bodies(self, db, seeded_cluster_data):
        raw_clusters = [
            {
                "size": 2,
                "centroid": [0.1, 0.2],
                "representative_ids": ["c1", "missing", "c2"],
            }
        ]

        result = clusters_router._build_cluster_display(raw_clusters, db)

        assert result == [
            {
                "size": 2,
                "centroid": [0.1, 0.2],
                "representatives": ["クラスタコメント1", "クラスタコメント2"],
            }
        ]


class TestClusterExplorer:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/u/nobody/clusters")

        assert resp.status_code == 404
        assert "ユーザが見つかりませんでした" in resp.text

    def test_renders_clusters(self, client, seeded_cluster_data, monkeypatch):
        monkeypatch.setattr(
            clusters_router.faiss_search,
            "get_clusters",
            lambda *_args, **_kwargs: [
                {
                    "size": 2,
                    "centroid": [0.1, 0.2],
                    "representative_ids": ["c1", "c2"],
                }
            ],
        )

        resp = client.get("/u/viewer/clusters?n_clusters=6")

        assert resp.status_code == 200
        assert "クラスタコメント1" in resp.text
        assert "クラスタコメント2" in resp.text

    def test_renders_error_when_backend_fails(self, client, seeded_cluster_data, monkeypatch):
        def _raise(*_args, **_kwargs):
            raise RuntimeError("cluster backend down")

        monkeypatch.setattr(clusters_router.faiss_search, "get_clusters", _raise)

        resp = client.get("/u/viewer/clusters")

        assert resp.status_code == 200
        assert "cluster backend down" in resp.text


class TestClusterCommentsPage:
    def test_renders_comments(self, client, seeded_cluster_data, monkeypatch):
        monkeypatch.setattr(clusters_router.faiss_search, "get_cluster_members", lambda *_args, **_kwargs: ["c1"])

        resp = client.post(
            "/u/viewer/cluster-comments",
            data={"centroid": "[0.1, 0.2]", "n_members": 5, "platform": "twitch"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        assert "クラスタコメント1" in resp.text

    def test_renders_error_when_backend_fails(self, client, seeded_cluster_data, monkeypatch):
        def _raise(*_args, **_kwargs):
            raise RuntimeError("members backend down")

        monkeypatch.setattr(clusters_router.faiss_search, "get_cluster_members", _raise)

        resp = client.post(
            "/u/viewer/cluster-comments",
            data={"centroid": "[0.1, 0.2]", "n_members": 5, "platform": "twitch"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert resp.status_code == 200
        assert "members backend down" in resp.text


class TestSubclusterApi:
    def test_returns_subclusters_as_json(self, client, seeded_cluster_data, monkeypatch):
        monkeypatch.setattr(
            clusters_router.faiss_search,
            "get_subclusters",
            lambda *_args, **_kwargs: [
                {
                    "size": 2,
                    "centroid": [0.3, 0.4],
                    "representative_ids": ["c1", "c2"],
                }
            ],
        )

        resp = client.post(
            "/u/viewer/clusters/subcluster",
            json={"centroid": [0.1, 0.2], "n_members": 10, "n_clusters": 4},
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "subclusters": [
                {
                    "size": 2,
                    "centroid": [0.3, 0.4],
                    "representatives": ["クラスタコメント1", "クラスタコメント2"],
                }
            ]
        }

    def test_returns_500_when_backend_fails(self, client, seeded_cluster_data, monkeypatch):
        def _raise(*_args, **_kwargs):
            raise RuntimeError("subcluster backend down")

        monkeypatch.setattr(clusters_router.faiss_search, "get_subclusters", _raise)

        resp = client.post(
            "/u/viewer/clusters/subcluster",
            json={"centroid": [0.1, 0.2], "n_members": 10, "n_clusters": 4},
        )

        assert resp.status_code == 500
        assert resp.json()["error"] == "subcluster backend down"
