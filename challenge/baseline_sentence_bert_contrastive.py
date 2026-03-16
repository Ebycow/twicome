"""Sentence-BERT + 軽量対照学習アダプタベースライン

固定 Sentence-BERT 埋め込みの上に線形射影を学習し、
本人同士を近づけ、本人と他人を離すように対照学習する。
フル fine-tune より軽く、短文タスク向けの適応を試しやすい実装。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_contrastive.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
    encode_texts,
    fetch_task,
    rank_question,
    submit_answers,
    topk_mean_max,
    training_bodies,
    training_labels,
)

TOP_K = 8
PAIR_BATCH_SIZE = 256
PAIR_STEPS = 64
EPOCHS = 4
RANDOM_STATE = 42


def knn_score(query_embeddings: np.ndarray, target_embeddings: np.ndarray) -> np.ndarray:
    similarities = query_embeddings @ target_embeddings.T
    mean_scores, max_scores = topk_mean_max(similarities, TOP_K)
    return 0.7 * mean_scores + 0.3 * max_scores


def train_projection(embeddings: np.ndarray, labels: np.ndarray):
    import torch
    import torch.nn.functional as F

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    rng = np.random.default_rng(RANDOM_STATE)

    positive_idx = np.flatnonzero(labels)
    negative_idx = np.flatnonzero(~labels)
    dim = embeddings.shape[1]

    layer = torch.nn.Linear(dim, dim, bias=False).to(device)
    with torch.no_grad():
        layer.weight.copy_(torch.eye(dim, device=device))

    optimizer = torch.optim.AdamW(layer.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_fn = torch.nn.CosineEmbeddingLoss(margin=0.2)

    train_tensor = torch.from_numpy(embeddings).to(device)

    for epoch in range(EPOCHS):
        total_loss = 0.0
        for _ in range(PAIR_STEPS):
            half = PAIR_BATCH_SIZE // 2

            pos_left = rng.choice(positive_idx, size=half, replace=True)
            pos_right = rng.choice(positive_idx, size=half, replace=True)
            overlap = pos_left == pos_right
            if overlap.any():
                replacement_pos = rng.choice(positive_idx, size=overlap.sum(), replace=True)
                pos_right[overlap] = replacement_pos

            neg_left = rng.choice(positive_idx, size=half, replace=True)
            neg_right = rng.choice(negative_idx, size=half, replace=True)

            left_indices = np.concatenate([pos_left, neg_left])
            right_indices = np.concatenate([pos_right, neg_right])
            pair_labels = np.concatenate([np.ones(half), -np.ones(half)]).astype(np.float32)

            left = train_tensor[torch.from_numpy(left_indices).to(device)]
            right = train_tensor[torch.from_numpy(right_indices).to(device)]
            target = torch.from_numpy(pair_labels).to(device)

            optimizer.zero_grad()
            proj_left = F.normalize(layer(left), dim=1)
            proj_right = F.normalize(layer(right), dim=1)
            loss = loss_fn(proj_left, proj_right, target)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())

        print(f"  contrastive adapter epoch {epoch + 1}/{EPOCHS}: loss={total_loss / PAIR_STEPS:.4f}")

    return layer


def project_embeddings(embeddings: np.ndarray, layer) -> np.ndarray:
    import torch
    import torch.nn.functional as F

    device = next(layer.parameters()).device
    outputs = []
    with torch.no_grad():
        for start in range(0, len(embeddings), 1024):
            batch = torch.from_numpy(embeddings[start : start + 1024]).to(device)
            projected = F.normalize(layer(batch), dim=1).cpu().numpy().astype(np.float32)
            outputs.append(projected)
    return np.vstack(outputs)


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)

    print(f"  学習データをエンコード中 ({len(X_train_texts)} 件)...")
    train_embeddings = encode_texts(model_name, X_train_texts, view="raw")

    print("  対照学習アダプタを学習中...")
    projection = train_projection(train_embeddings, y_train)
    adapted_train = project_embeddings(train_embeddings, projection)
    target_embeddings = adapted_train[y_train]

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補をエンコード中 ({len(all_bodies)} 件)...")
    candidate_embeddings = encode_texts(model_name, all_bodies, view="raw")
    adapted_candidates = project_embeddings(candidate_embeddings, projection)

    answers = []
    for q_idx, question in enumerate(test):
        q_embeddings = adapted_candidates[q_idx * n_cand : (q_idx + 1) * n_cand]
        answers.append(rank_question(question, knn_score(q_embeddings, target_embeddings)))
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformer モデル名")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(
        f"  学習データ: {task['train_count']} 件, "
        f"テスト: {task['test_count']} 問 × {task['candidates_per_question']} 候補"
    )

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"], args.model)

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print("\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
