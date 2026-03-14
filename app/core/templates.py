"""Jinja2 テンプレートエンジン設定"""

from fastapi.templating import Jinja2Templates

from core.config import ROOT_PATH, STATIC_VERSION

templates = Jinja2Templates(directory="templates")
templates.env.globals["root_path"] = ROOT_PATH
templates.env.globals["static_version"] = STATIC_VERSION
