"""FAISS API サービス

埋め込みモデルとFAISSインデックス管理を一元化するサービス。
app と batch からHTTP経由で利用する。
"""

import json
import os
import threading
from pathlib import Path

import faiss
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# --- 設定 ---
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "hotchpotch/static-embedding-japanese")
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "512"))
CONFIG_PATH = Path(os.getenv("FAISS_CONFIG_PATH", "/app/faiss_config.json"))

# faiss_config.json から感情アンカーを読み込む
# 形式: {"joy": {"positive": [...], "negative": [...]}, ...}
_emotion_anchors_config: dict[str, dict[str, list[str]]] = {}
if CONFIG_PATH.is_file():
    with open(CONFIG_PATH) as _f:
        _cfg = json.load(_f)
        _emotion_anchors_config = _cfg.get("emotion_anchors", {})

app = FastAPI(title="FAISS API", version="1.0.0")

# --- シングルトン: 埋め込みモデル ---
_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


# --- 感情アンカーの埋め込みキャッシュ ---
_emotion_embeddings: dict[str, np.ndarray] | None = None
_emotion_lock = threading.Lock()


def get_emotion_embeddings() -> dict[str, np.ndarray]:
    """各感情の双極軸ベクトルを返す。

    positive - negative の方向を正規化したベクトル。
    """
    global _emotion_embeddings
    if _emotion_embeddings is None:
        with _emotion_lock:
            if _emotion_embeddings is None:
                model = get_model()
                _emotion_embeddings = {}
                for key, anchors in _emotion_anchors_config.items():
                    pos_texts = anchors.get("positive", [])
                    neg_texts = anchors.get("negative", [])
                    if not pos_texts:
                        continue
                    pos_vecs = model.encode(pos_texts, normalize_embeddings=True)
                    pos_centroid = np.mean(pos_vecs, axis=0)
                    if neg_texts:
                        neg_vecs = model.encode(neg_texts, normalize_embeddings=True)
                        neg_centroid = np.mean(neg_vecs, axis=0)
                        direction = pos_centroid - neg_centroid
                    else:
                        direction = pos_centroid
                    norm = np.linalg.norm(direction)
                    if norm > 1e-8:
                        direction = direction / norm
                    _emotion_embeddings[key] = np.array(direction, dtype=np.float32)
                print(f"[faiss-api] 感情双極軸ベクトル計算完了: {list(_emotion_embeddings.keys())}")
    return _emotion_embeddings


# --- ユーザ別インデックス管理 ---
class UserIndex:
    """ユーザ1人分のFAISSインデックスを管理する"""

    def __init__(self, login: str):
        self.login = login
        self.index: faiss.Index | None = None
        self.comment_ids: list[str] = []
        self.knn_densities: list[float] | None = None  # k近傍平均類似度（典型度スライダー用）
        self.lock = threading.Lock()

    @property
    def index_path(self) -> Path:
        return DATA_DIR / f"{self.login}.faiss"

    @property
    def meta_path(self) -> Path:
        return DATA_DIR / f"{self.login}.meta.json"

    def is_available(self) -> bool:
        return self.index_path.exists() and self.meta_path.exists()

    def load(self):
        """ディスクからインデックスを読み込む（ロック内から呼ぶこと）"""
        self.index = faiss.read_index(str(self.index_path))
        with open(self.meta_path) as f:
            meta = json.load(f)
        self.comment_ids = meta["comment_ids"]
        # knn_densities が無い古いファイルは centroid_similarities にフォールバック
        self.knn_densities = meta.get("knn_densities") or meta.get("centroid_similarities")
        print(f"[faiss-api] インデックス読み込み [{self.login}]: {len(self.comment_ids)} 件")

    def ensure_loaded(self):
        """インデックスが未ロードなら読み込む"""
        with self.lock:
            if self.index is None and self.is_available():
                self.load()

    def update(self, new_ids: list[str], new_embeddings: np.ndarray) -> int:
        """新規埋め込みをインデックスに追加し、重心を再計算してアトミック保存する。追加件数を返す"""
        with self.lock:
            dim = new_embeddings.shape[1]

            if self.index is None:
                if self.is_available():
                    self.load()
                else:
                    self.index = faiss.IndexFlatIP(dim)
                    self.comment_ids = []

            # ロック内で再チェック（並行リクエスト対策）
            existing_ids = set(self.comment_ids)
            mask = [i for i, cid in enumerate(new_ids) if cid not in existing_ids]
            if not mask:
                return 0
            new_ids = [new_ids[i] for i in mask]
            new_embeddings = new_embeddings[mask]

            self.index.add(new_embeddings)
            self.comment_ids.extend(new_ids)

            # KNN密度を再計算（典型度スライダー用）
            # 各コメントについて、k近傍のコサイン類似度の平均を密度とする
            # 密度が高い = 似たコメントが多い = 典型的
            n_total = self.index.ntotal
            k = min(20, n_total - 1)
            if k > 0:
                all_vectors = np.empty((n_total, dim), dtype=np.float32)
                for i in range(n_total):
                    all_vectors[i] = self.index.reconstruct(i)
                D, _ = self.index.search(all_vectors, k + 1)  # +1 は自分自身を含む
                # D[:, 0] ≈ 1.0（自分自身）を除いて平均
                self.knn_densities = D[:, 1:k + 1].mean(axis=1).tolist()
            else:
                self.knn_densities = [1.0] * n_total

            # アトミック書き込み
            tmp_index = str(self.index_path) + ".tmp"
            tmp_meta = str(self.meta_path) + ".tmp"
            faiss.write_index(self.index, tmp_index)
            meta = {
                "comment_ids": self.comment_ids,
                "total_comments": len(self.comment_ids),
                "embedding_dim": dim,
                "knn_densities": self.knn_densities,
            }
            with open(tmp_meta, "w") as f:
                json.dump(meta, f, ensure_ascii=False)
            os.replace(tmp_index, str(self.index_path))
            os.replace(tmp_meta, str(self.meta_path))

            return len(new_ids)

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """類似検索。[(comment_id, score), ...] を返す"""
        k = min(top_k, self.index.ntotal)
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        scores, indices = self.index.search(query_embedding, k)
        results = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if 0 <= idx < len(self.comment_ids):
                results.append((self.comment_ids[idx], float(score)))
        return results

    def search_centroid(self, position: float, top_k: int) -> list[tuple[str, float]]:
        """典型度検索。position=0.0→典型的(密度高), 1.0→珍しい(密度低)"""
        if self.knn_densities is None:
            return []
        pairs = list(enumerate(self.knn_densities))
        # 密度降順: index 0 が最も典型的
        pairs.sort(key=lambda x: x[1], reverse=True)
        total = len(pairs)
        max_offset = max(0, total - top_k)
        offset = min(int(position * max_offset), max_offset)
        selected = pairs[offset:offset + top_k]
        return [(self.comment_ids[idx], sim) for idx, sim in selected]


# ユーザ別インデックスのレジストリ
_user_indexes: dict[str, UserIndex] = {}
_registry_lock = threading.Lock()


def get_user_index(login: str) -> UserIndex:
    if login not in _user_indexes:
        with _registry_lock:
            if login not in _user_indexes:
                ui = UserIndex(login)
                if ui.is_available():
                    ui.load()
                _user_indexes[login] = ui
    return _user_indexes[login]


# --- リクエスト/レスポンスモデル ---
class EmbedRequest(BaseModel):
    """テキスト埋め込みリクエスト。"""

    texts: list[str]
    normalize: bool = True


class IndexUpdateRequest(BaseModel):
    """インデックス更新リクエスト。"""

    comment_ids: list[str]
    texts: list[str]


class SimilarSearchRequest(BaseModel):
    """意味的類似検索リクエスト。"""

    query: str
    top_k: int = 20


class CentroidSearchRequest(BaseModel):
    """重心距離検索リクエスト。"""

    position: float = 0.5
    top_k: int = 50


class EmotionSearchRequest(BaseModel):
    """感情アンカー検索リクエスト。"""

    weights: dict[str, float]
    top_k: int = 50


class SubclusterRequest(BaseModel):
    """サブクラスタリングリクエスト。"""

    centroid: list[float]        # 親クラスタの正規化済み重心ベクトル
    n_members: int               # 親クラスタのサイズ（検索上限として使用）
    n_clusters: int = 4          # サブクラスタ数


class ClusterMembersRequest(BaseModel):
    """クラスタメンバー取得リクエスト。"""

    centroid: list[float]        # クラスタの正規化済み重心ベクトル
    n_members: int               # 取得する件数


# --- 起動時処理 ---
@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[faiss-api] モデル読み込み中: {MODEL_NAME}")
    get_model()
    if _emotion_anchors_config:
        get_emotion_embeddings()
    print(f"[faiss-api] 起動完了。データディレクトリ: {DATA_DIR}")


# --- エンドポイント ---
@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/embed")
def embed(req: EmbedRequest):
    if not req.texts:
        return {"embeddings": []}
    model = get_model()
    embeddings = model.encode(req.texts, normalize_embeddings=req.normalize)
    return {"embeddings": embeddings.tolist()}


@app.get("/emotion_axes")
def emotion_axes():
    labels = {
        "joy": "笑い・楽しさ",
        "surprise": "驚き",
        "admiration": "称賛・感動",
        "anger": "怒り・不満",
        "sadness": "悲しみ",
        "cheer": "応援",
    }
    axes = [{"key": k, "label": labels.get(k, k)} for k in _emotion_anchors_config]
    return {"axes": axes}


@app.get("/index/{login}/status")
def index_status(login: str):
    ui = get_user_index(login)
    if not ui.is_available():
        raise HTTPException(status_code=404, detail="index_not_available")
    return {"login": login, "total": len(ui.comment_ids)}


@app.post("/index/update/{login}")
def update_index(login: str, req: IndexUpdateRequest):
    if len(req.comment_ids) != len(req.texts):
        raise HTTPException(status_code=400, detail="comment_ids と texts の件数が一致しません")

    ui = get_user_index(login)

    model = get_model()
    embeddings = model.encode(
        req.texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    embeddings = np.array(embeddings, dtype=np.float32)

    added = ui.update(req.comment_ids, embeddings)
    print(f"[faiss-api] インデックス更新 [{login}]: +{added} 件, 合計 {len(ui.comment_ids)} 件")

    return {"status": "ok", "added": added, "total": len(ui.comment_ids), "login": login}


@app.get("/index/clusters/{login}")
def get_clusters(login: str, n_clusters: int = 8):
    """K-means クラスタリングで発言パターンを分類する。

    各クラスタの件数と代表コメントID (重心に近い上位3件) を返す。
    """
    ui = get_user_index(login)
    if not ui.is_available() or ui.index is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    with ui.lock:
        n_total = ui.index.ntotal
        dim = ui.index.d
        actual_k = min(n_clusters, n_total)

        all_vectors = np.empty((n_total, dim), dtype=np.float32)
        for i in range(n_total):
            all_vectors[i] = ui.index.reconstruct(i)

        # 正規化ベクトルに対して球面K-means（内積最大化）
        kmeans = faiss.Kmeans(dim, actual_k, niter=20, seed=42, spherical=True)
        kmeans.train(all_vectors)

        # 各コメントのクラスタ割り当てを取得
        _, assignments = kmeans.index.search(all_vectors, 1)
        assignments = assignments.reshape(-1)

        clusters = []
        for c in range(actual_k):
            mask = np.where(assignments == c)[0]
            if len(mask) == 0:
                continue
            cluster_vecs = all_vectors[mask]
            centroid = kmeans.centroids[c].copy()
            norm = np.linalg.norm(centroid)
            if norm > 1e-8:
                centroid = centroid / norm
            # 重心との内積（コサイン類似度）でソートして上位10件
            sims = cluster_vecs @ centroid
            top_local = np.argsort(sims)[::-1][:10]
            rep_ids = [ui.comment_ids[mask[i]] for i in top_local]
            clusters.append({
                "cluster_id": int(c),
                "size": int(len(mask)),
                "representative_ids": rep_ids,
                "centroid": centroid.tolist(),  # サブクラスタリング用
            })

        # 件数の多い順にソート
        clusters.sort(key=lambda x: x["size"], reverse=True)

    return {"clusters": clusters, "total": n_total}


@app.post("/index/subcluster/{login}")
def subcluster(login: str, req: SubclusterRequest):
    """親クラスタの重心ベクトルを使ってサブクラスタリングを行う。

    重心に近い上位 n_members 件を取得し、その中でさらに K-means を実行する。
    """
    ui = get_user_index(login)
    if not ui.is_available() or ui.index is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    centroid = np.array(req.centroid, dtype=np.float32).reshape(1, -1)
    n_members = min(req.n_members, ui.index.ntotal)
    actual_k = min(req.n_clusters, n_members)

    with ui.lock:
        dim = ui.index.d
        # 親クラスタの重心に近い上位 n_members 件を取得
        D, index = ui.index.search(centroid, n_members)
        member_indices = index[0]

        member_vecs = np.empty((len(member_indices), dim), dtype=np.float32)
        for i, idx in enumerate(member_indices):
            member_vecs[i] = ui.index.reconstruct(int(idx))

        # メンバーの中でさらにK-means
        kmeans = faiss.Kmeans(dim, actual_k, niter=20, seed=42, spherical=True)
        kmeans.train(member_vecs)

        _, assignments = kmeans.index.search(member_vecs, 1)
        assignments = assignments.reshape(-1)

        subclusters = []
        for c in range(actual_k):
            sub_mask = np.where(assignments == c)[0]
            if len(sub_mask) == 0:
                continue
            sub_vecs = member_vecs[sub_mask]
            sub_centroid = kmeans.centroids[c].copy()
            norm = np.linalg.norm(sub_centroid)
            if norm > 1e-8:
                sub_centroid = sub_centroid / norm
            sims = sub_vecs @ sub_centroid
            top_local = np.argsort(sims)[::-1][:10]
            rep_ids = [ui.comment_ids[member_indices[sub_mask[i]]] for i in top_local]
            subclusters.append({
                "cluster_id": int(c),
                "size": int(len(sub_mask)),
                "representative_ids": rep_ids,
                "centroid": sub_centroid.tolist(),
            })

        subclusters.sort(key=lambda x: x["size"], reverse=True)

    return {"subclusters": subclusters}


@app.post("/index/cluster_members/{login}")
def cluster_members(login: str, req: ClusterMembersRequest):
    """クラスタの重心に近い上位 n_members 件のコメントIDを返す。"""
    ui = get_user_index(login)
    if not ui.is_available() or ui.index is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    centroid = np.array(req.centroid, dtype=np.float32).reshape(1, -1)
    n_members = min(req.n_members, ui.index.ntotal)

    with ui.lock:
        _, index = ui.index.search(centroid, n_members)
        member_ids = [ui.comment_ids[int(idx)] for idx in index[0] if 0 <= int(idx) < len(ui.comment_ids)]

    return {"comment_ids": member_ids}


@app.post("/index/rebuild_densities/{login}")
def rebuild_densities(login: str):
    """既存インデックスのKNN密度を再計算してmeta.jsonを更新する。再埋め込みは不要。"""
    ui = get_user_index(login)
    if not ui.is_available():
        raise HTTPException(status_code=404, detail="index_not_available")

    with ui.lock:
        if ui.index is None:
            ui.load()

        n_total = ui.index.ntotal
        dim = ui.index.d
        k = min(20, n_total - 1)
        if k > 0:
            all_vectors = np.empty((n_total, dim), dtype=np.float32)
            for i in range(n_total):
                all_vectors[i] = ui.index.reconstruct(i)
            D, _ = ui.index.search(all_vectors, k + 1)
            ui.knn_densities = D[:, 1:k + 1].mean(axis=1).tolist()
        else:
            ui.knn_densities = [1.0] * n_total

        tmp_meta = str(ui.meta_path) + ".tmp"
        meta = {
            "comment_ids": ui.comment_ids,
            "total_comments": len(ui.comment_ids),
            "embedding_dim": dim,
            "knn_densities": ui.knn_densities,
        }
        with open(tmp_meta, "w") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmp_meta, str(ui.meta_path))

    print(f"[faiss-api] KNN密度再計算完了 [{login}]: {n_total} 件")
    return {"status": "ok", "login": login, "total": n_total}


@app.post("/search/similar/{login}")
def search_similar(login: str, req: SimilarSearchRequest):
    ui = get_user_index(login)
    if not ui.is_available() or ui.index is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    model = get_model()
    query_emb = model.encode([req.query], normalize_embeddings=True)
    query_emb = np.array(query_emb, dtype=np.float32)

    with ui.lock:
        results = ui.search(query_emb, req.top_k)

    return {"results": [{"comment_id": cid, "score": score} for cid, score in results]}


@app.post("/search/centroid/{login}")
def search_centroid(login: str, req: CentroidSearchRequest):
    ui = get_user_index(login)
    if not ui.is_available() or ui.knn_densities is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    with ui.lock:
        results = ui.search_centroid(req.position, req.top_k)

    return {"results": [{"comment_id": cid, "score": score} for cid, score in results]}


@app.post("/search/emotion/{login}")
def search_emotion(login: str, req: EmotionSearchRequest):
    ui = get_user_index(login)
    if not ui.is_available() or ui.index is None:
        raise HTTPException(status_code=404, detail="index_not_available")

    emotion_embs = get_emotion_embeddings()
    active_weights = {k: v for k, v in req.weights.items() if v > 0 and k in emotion_embs}
    if not active_weights:
        raise HTTPException(status_code=400, detail="有効な感情ウェイトが設定されていません")

    dim = next(iter(emotion_embs.values())).shape[0]
    combined = np.zeros(dim, dtype=np.float32)
    for key, weight in active_weights.items():
        combined += weight * emotion_embs[key]

    norm = np.linalg.norm(combined)
    if norm < 1e-8:
        raise HTTPException(status_code=400, detail="合成ベクトルがゼロです")
    combined = (combined / norm).reshape(1, -1)

    with ui.lock:
        results = ui.search(combined, req.top_k)

    return {"results": [{"comment_id": cid, "score": score} for cid, score in results]}
