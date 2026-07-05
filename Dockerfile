# 공개 '약사 시급 리포트' 배포본 (Cloud Run)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings_prod

WORKDIR /app

# 웹 배포본 전용 최소 의존성만 설치
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# 앱 코드 (.gcloudignore 로 걸러진 소스만 업로드됨)
COPY . .

# 정적 파일 수집 (whitenoise 가 런타임에 서빙)
RUN python manage.py collectstatic --noinput

# Cloud Run 은 $PORT(기본 8080)로 트래픽을 보낸다
EXPOSE 8080
CMD exec gunicorn config.wsgi:application \
    --bind :${PORT:-8080} \
    --workers 2 --threads 4 --timeout 60
