"""哲思门面 API（骨架期）。

/healthz 探活、/api/version 版本。骨架期 CORS 全开（照 fd-lex 骨架先例），
接线期收敛。个人层 API（立场卡等，task 3.x）后续在此挂载。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__

app = FastAPI(title="fd-zhesi-api", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "fd-zhesi-api", "version": __version__}


@app.get("/api/version")
def version() -> dict:
    return {"service": "fd-zhesi-api", "version": __version__}
