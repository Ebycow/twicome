"""形態素解析 API

SudachiPy (sudachidict-full) による日本語形態素解析サービス。
モード A（最小単位）/ B（中間）/ C（最大単位）に対応。
辞書更新は sudachidict-full のバージョンアップと共にイメージ再ビルドで行う。
"""

import logging
import threading
from typing import Literal

import sudachipy
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="morpheme-api")
logger = logging.getLogger("morpheme-api")
logging.basicConfig(level=logging.INFO)

_MODE_MAP = {
    "A": sudachipy.SplitMode.A,
    "B": sudachipy.SplitMode.B,
    "C": sudachipy.SplitMode.C,
}

_dictionary: sudachipy.Dictionary | None = None
_dict_lock = threading.Lock()


def get_dictionary() -> sudachipy.Dictionary:
    """辞書インスタンスをシングルトンで返す（初回のみロード）。"""
    global _dictionary
    if _dictionary is None:
        with _dict_lock:
            if _dictionary is None:
                logger.info("sudachi 辞書をロード中...")
                _dictionary = sudachipy.Dictionary(dict="full")
                logger.info("sudachi 辞書ロード完了")
    return _dictionary


def _tokenize(text: str, mode: str) -> list[dict]:
    # Dictionary.create() はスレッドセーフなので呼び出しごとに生成
    tokenizer = get_dictionary().create(mode=_MODE_MAP[mode])
    morphemes = tokenizer.tokenize(text)
    result = []
    for m in morphemes:
        pos = m.part_of_speech()
        result.append(
            {
                "surface": m.surface(),
                "reading": m.reading_form(),
                "pos": pos[0],
                "pos_detail": pos[1],
                "base_form": m.dictionary_form(),
                "normalized_form": m.normalized_form(),
            }
        )
    return result


class AnalyzeRequest(BaseModel):
    """形態素解析リクエスト。"""

    texts: list[str] = Field(..., max_length=1000)
    mode: Literal["A", "B", "C"] = "C"


class AnalyzeResponse(BaseModel):
    """形態素解析レスポンス。"""

    results: list[list[dict]]
    mode: str


@app.on_event("startup")
def startup() -> None:
    """起動時に辞書をプリロードする。"""
    get_dictionary()


@app.get("/health")
def health() -> dict:
    """ヘルスチェック。"""
    return {"status": "ok", "dictionary": "sudachidict-full"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """テキストリストを形態素解析して返す。"""
    if not req.texts:
        return AnalyzeResponse(results=[], mode=req.mode)
    try:
        results = [_tokenize(t, req.mode) for t in req.texts]
    except Exception as e:
        logger.exception("形態素解析エラー")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return AnalyzeResponse(results=results, mode=req.mode)
