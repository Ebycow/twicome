"""Jinja2 テンプレートエンジン設定"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from core.config import ROOT_PATH, STATIC_VERSION

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["root_path"] = ROOT_PATH
templates.env.globals["static_version"] = STATIC_VERSION
