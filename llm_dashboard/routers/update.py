from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from llm_dashboard.services.updater import self_update

router = APIRouter(prefix="/api", tags=["update"])


@router.post("/update")
async def update(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "error": "invalid body"}, status_code=400)

    target = payload.get("target")
    if not target:
        return JSONResponse({"success": False, "error": "missing target"}, status_code=400)

    return self_update(target)
