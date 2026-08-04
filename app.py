import sys
import os
from pathlib import Path

# نضيف مسار المجلد الحالي للنظام لضمان العثور على الملفات
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# استيراد تطبيق FastAPI من ملف checker_api2
from checker_api2 import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 6767))
    print(f"Starting VeNoM Checker API on port {port}...")
    print(f"Endpoint: /VeNoM-xK9qPm2r")
    print(f"Status  : /VeNoM-status")
    uvicorn.run(app, host="0.0.0.0", port=port)