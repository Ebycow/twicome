"""VOD チャットをダウンロードし、収集対象ユーザーを含む配信だけ gzip で保存する。

- 対象ユーザーのコメントを含む VOD: ``<COMMENTS_DIR>/<vod_id>.json.gz`` として保存
- 含まない VOD: ファイルは破棄し、``<COMMENTS_DIR>/no_target_vods.tsv`` に記録して再ダウンロードを防ぐ

台帳には判定時の対象ログイン一覧も記録する。対象ユーザーが追加された場合、
その VOD は追加ユーザーについて未判定なので再ダウンロードして判定し直す。
"""

import csv
import gzip
import os
import shutil
import subprocess
from pathlib import Path

from collect_targets import has_target_comment, load_chat_json, load_target_logins

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "default"
LEDGER_FILENAME = "no_target_vods.tsv"
TMP_DIRNAME = ".download_tmp"


def resolve_downloader() -> Path:
    """TwitchDownloaderCLI のパスを解決し、実行可能か検証する。"""
    downloader_env = os.getenv("TWITCH_DOWNLOADER_CLI")
    if downloader_env:
        downloader = Path(downloader_env).expanduser()
        if not downloader.is_absolute():
            downloader = PROJECT_ROOT / downloader
    else:
        downloader = PROJECT_ROOT / "library" / "TwitchDownloaderCLI"

    if not downloader.exists():
        raise FileNotFoundError(
            f"TwitchDownloaderCLI not found at {downloader}. Set TWITCH_DOWNLOADER_CLI to override."
        )
    if not os.access(downloader, os.X_OK):
        raise PermissionError(f"TwitchDownloaderCLI is not executable: {downloader}")
    return downloader


def load_ledger(path: Path) -> dict[str, frozenset[str]]:
    """台帳を読み込み {vod_id: 判定済みログイン集合} を返す。"""
    ledger: dict[str, frozenset[str]] = {}
    if not path.exists():
        return ledger
    for line in path.read_text(encoding="utf-8").splitlines():
        vod_id, _, logins = line.partition("\t")
        if vod_id.strip():
            ledger[vod_id.strip()] = frozenset(x for x in logins.split(",") if x)
    return ledger


def append_ledger(path: Path, vod_id: str, targets: frozenset[str]) -> None:
    """対象ユーザー不在の VOD を台帳へ追記する。"""
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{vod_id}\t{','.join(sorted(targets))}\n")


def already_handled(comments_dir: Path, vod_id: str, ledger: dict[str, frozenset[str]], targets) -> bool:
    """保存済み、または現在の対象ユーザー全員について判定済みなら True。"""
    for name in (f"{vod_id}.json.gz", f"{vod_id}.json"):
        p = comments_dir / name
        if p.exists() and p.stat().st_size > 0:
            return True
    checked = ledger.get(vod_id)
    return checked is not None and targets <= checked


def gzip_file(src: Path, dest: Path) -> None:
    """ファイルを gzip 圧縮し、出力先へアトミックに書き出す。"""
    tmp = dest.with_name(dest.name + ".part")
    with src.open("rb") as fin, gzip.open(tmp, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)
    tmp.replace(dest)


def process_vod(downloader: Path, url: str, vod_id: str, comments_dir: Path, tmp_dir: Path, targets) -> str:
    """1 VOD をダウンロード・判定する。'kept' / 'discarded' / 'error' を返す。"""
    # TwitchDownloaderCLI は出力拡張子で形式を決めるため .json で終える
    tmp_json = tmp_dir / f"{vod_id}.json"
    try:
        subprocess.run([str(downloader), "chatdownload", "--id", url, "-o", str(tmp_json)], check=True)
        if not tmp_json.exists() or tmp_json.stat().st_size == 0:
            print(f"Error downloading {vod_id}: empty output")
            return "error"

        data = load_chat_json(tmp_json)
        if has_target_comment(data, targets):
            del data  # 圧縮中に大きな dict を抱えないよう先に解放
            gzip_file(tmp_json, comments_dir / f"{vod_id}.json.gz")
            print(f"Kept {vod_id}: contains target users")
            return "kept"
        print(f"Discarded {vod_id}: no target users")
        return "discarded"
    except subprocess.CalledProcessError as e:
        print(f"Error downloading {vod_id}: {e}")
        return "error"
    except ValueError as e:  # JSON 破損
        print(f"Error parsing {vod_id}: {e}")
        return "error"
    finally:
        tmp_json.unlink(missing_ok=True)


def main() -> None:
    """VOD CSV を順に処理する。"""
    csv_file = Path(os.getenv("VODS_CSV", str(DEFAULT_DATA_DIR / "batch_twitch_vods_all.csv")))
    comments_dir = Path(os.getenv("COMMENTS_DIR", str(DEFAULT_DATA_DIR / "comments")))
    targets = load_target_logins()
    downloader = resolve_downloader()

    if not csv_file.exists():
        raise FileNotFoundError(
            f"VOD CSV not found: {csv_file}. Run get_vod_list_batch.py first or set VODS_CSV to override."
        )

    comments_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = comments_dir / TMP_DIRNAME
    shutil.rmtree(tmp_dir, ignore_errors=True)  # 前回中断分を掃除
    tmp_dir.mkdir()
    ledger_path = comments_dir / LEDGER_FILENAME
    ledger = load_ledger(ledger_path)
    print(f"Target users: {', '.join(sorted(targets))}")

    counts = {"kept": 0, "discarded": 0, "error": 0, "skipped": 0}
    try:
        with csv_file.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = row["url"]
                vod_id = url.rstrip("/").split("/")[-1]
                if already_handled(comments_dir, vod_id, ledger, targets):
                    counts["skipped"] += 1
                    continue
                result = process_vod(downloader, url, vod_id, comments_dir, tmp_dir, targets)
                counts[result] += 1
                if result == "discarded":
                    append_ledger(ledger_path, vod_id, targets)
                    ledger[vod_id] = targets
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(
        "Done. kept={kept}, discarded={discarded}, error={error}, skipped={skipped}".format(**counts),
    )


if __name__ == "__main__":
    main()
