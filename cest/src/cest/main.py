from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cest.routes.evaluate import router as evaluate_router
from cest.routes.parse_csv import router as parse_csv_router

app = FastAPI(title="CEST API", version="v0.3.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(evaluate_router)
app.include_router(parse_csv_router)


# Lambda (AWS) で実行されるときは Mangum 経由で ASGI を ALB/API Gateway に橋渡しする。
# ローカル開発時は mangum 未インストールでも uvicorn から動かせるよう、importは任意。
try:
    from mangum import Mangum

    handler = Mangum(app)
except ImportError:
    handler = None
