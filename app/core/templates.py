from fastapi.templating import Jinja2Templates

from core.config import ROOT_PATH

templates = Jinja2Templates(directory="templates")
templates.env.globals["root_path"] = ROOT_PATH
