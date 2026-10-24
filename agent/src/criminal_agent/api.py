"""FastAPI サーバ: POST /consult で刑法相談の構造化回答を返す。"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import DISCLAIMER, ConsultationResult, consult, consult_stream

app = FastAPI(
    title="刑法相談エージェント API",
    description="日本の刑法に関する情報提供（法的助言ではない）。",
    version="0.1.0",
)

# CORS: 開発用に Vite(5173) を許可。環境変数でオリジン追加可。
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra = os.environ.get("CORS_ORIGINS", "")
_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConsultRequest(BaseModel):
    text: str = Field(min_length=1, description="相談文")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "disclaimer": DISCLAIMER}


@app.post("/consult", response_model=ConsultationResult)
def post_consult(req: ConsultRequest) -> ConsultationResult:
    """相談文を受けて構造化回答を返す。LLM(Bedrock)呼び出しを伴う。"""
    try:
        return consult(req.text)
    except Exception as e:  # noqa: BLE001 - API 境界でまとめて変換
        raise HTTPException(status_code=502, detail=f"agent error: {e}") from e


@app.post("/consult/stream")
async def post_consult_stream(req: ConsultRequest) -> StreamingResponse:
    """相談処理を Server-Sent Events でストリーミング配信する。

    各イベントは `data: <JSON>\\n\\n` 形式。JSON は agent.consult_stream の
    イベント dict（type: start/reasoning/token/tool_use/sparql/graph/
    tool_result/result/done/error）。
    """

    async def event_gen():
        try:
            async for event in consult_stream(req.text):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # プロキシのバッファリング抑止
        },
    )
