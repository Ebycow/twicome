"""Twitch VOD リスト取得バッチスクリプト。"""

import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH

load_dotenv(str(ENV_PATH))
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "default"


def get_live_user_ids(user_ids, access_token, client_id):
    """まとめて「今配信中のuser_id集合」を返す😺🦐"""
    headers = {"Client-ID": client_id, "Authorization": f"Bearer {access_token}"}

    live = set()
    # 100件ずつに分割
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i : i + 100]
        params = [("user_id", uid) for uid in chunk]
        r = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params)
        data = r.json()

        if r.status_code != 200:
            raise RuntimeError(f"Get Streams failed: {r.status_code} {data}")

        for s in data.get("data", []):
            live.add(str(s["user_id"]))

    return live


# ✅ VODデータを取得する関数（ページネーション対応）
def get_all_vods(user_id, access_token, client_id):
    """指定ユーザーの全 VOD データをページネーションで取得して返す。"""
    url = f"https://api.twitch.tv/helix/videos?user_id={user_id}&first=100"
    headers = {"Client-ID": client_id, "Authorization": f"Bearer {access_token}"}

    all_vods = []
    while url:
        response = requests.get(url, headers=headers)
        print(f"Response status: {response.status_code}")
        data = response.json()
        print(f"Response data keys: {list(data.keys())}")

        if response.status_code == 401:
            print(f"Error: Unauthorized. Message: {data.get('message', 'Unknown error')}")
            print("Please check your CLIENT_ID and ACCESS_TOKEN.")
            return []

        if "data" in data:
            print(f"Number of VODs in this page: {len(data['data'])}")
            all_vods.extend(data["data"])
        else:
            print("No 'data' key in response")

        # ✅ 次のページがあるかチェック
        pagination_cursor = data.get("pagination", {}).get("cursor")
        if pagination_cursor:
            url = f"https://api.twitch.tv/helix/videos?user_id={user_id}&first=100&after={pagination_cursor}"
        else:
            url = None  # 次のページがなければループ終了

    return all_vods


def main():
    """VOD リスト取得バッチのエントリーポイント。"""
    access_token = os.getenv("ACCESS_TOKEN")
    client_id = os.getenv("CLIENT_ID")
    target_users_csv = Path(os.getenv("TARGET_USERS_CSV", str(DEFAULT_DATA_DIR / "targetusers.csv")))
    vods_csv = Path(os.getenv("VODS_CSV", str(DEFAULT_DATA_DIR / "batch_twitch_vods_all.csv")))

    if not access_token:
        raise RuntimeError("ACCESS_TOKEN が .env に無い or 読めてないよ")
    if not target_users_csv.exists():
        raise FileNotFoundError(f"target users CSV not found: {target_users_csv}. Set TARGET_USERS_CSV to override.")

    # ✅ 複数のユーザー ID のリスト (targetusers.csv から読み込み)
    df_users = pd.read_csv(target_users_csv)
    user_ids = df_users["id"].astype(str).tolist()

    live_user_ids = get_live_user_ids(user_ids, access_token, client_id)

    all_vods_data = []

    # ✅ 各ユーザーに対して VOD を取得
    for user_id in user_ids:
        if user_id in live_user_ids:
            print(f"Skip user {user_id}: because currently LIVE")
            continue
        print(f"Fetching VODs for user ID: {user_id}")
        vods = get_all_vods(user_id, access_token, client_id)
        for vod in vods:
            vod["user_id"] = user_id  # ユーザー ID を追加
            all_vods_data.append(vod)

    # ✅ 取得したデータを DataFrame に変換
    df = pd.DataFrame(all_vods_data)

    # ✅ デバッグ: DataFrameのカラムを確認
    print("DataFrame columns:", df.columns.tolist())

    # ✅ 必要なカラムだけ選択（不要なデータを削除）
    required_columns = ["user_id", "id", "title", "created_at", "url", "view_count", "duration"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Error: Missing columns: {missing_columns}")
        print("Available columns:", df.columns.tolist())
        exit(1)
    df = df[required_columns]

    # ✅ CSV に保存（UTF-8 エンコーディング）
    vods_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(vods_csv, index=False, encoding="utf-8")

    print(f"すべての VOD データを '{vods_csv}' に保存しました！")


if __name__ == "__main__":
    main()
