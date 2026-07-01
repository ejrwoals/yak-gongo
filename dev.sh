#!/usr/bin/env bash
# 개발 서버 실행 스크립트
# 사용법: ./dev.sh [포트]   (포트 생략 시 8011)
set -euo pipefail

# 스크립트가 어디서 실행되든 프로젝트 루트 기준으로 동작
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
PORT="${1:-8011}"

# 가상환경 확인
if [ ! -x "$PYTHON" ]; then
  echo "⚠️  .venv 가상환경이 없습니다. 먼저 아래 명령으로 생성하세요:"
  echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# 마이그레이션 적용 후 서버 실행
echo "🔄 마이그레이션 적용 중..."
"$PYTHON" manage.py migrate

echo "🚀 개발 서버 실행 (http://127.0.0.1:${PORT})"
exec "$PYTHON" manage.py runserver "0.0.0.0:${PORT}"
