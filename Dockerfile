# أضف هذا السطر لتحديد إصدار بايثون (يمكنك تغييره لـ 3.9 أو 3.11 حسب مشروعك)
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
