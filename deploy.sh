#!/usr/bin/env bash
# 공개 '약사 시급 리포트'를 Google Cloud Run 에 배포한다.
#
#   ./deploy.sh
#
# 이 스크립트 하나로 배포가 끝난다:
#   1) 로컬 DB의 최신 스냅샷을 web/snapshot/latest.json 으로 export
#   2) 비밀값을 Secret Manager('gongo-' 네임스페이스)에 동기화 후 reference 연결
#        - DJANGO_SECRET_KEY   : 없으면 자동 생성
#        - SUPABASE_JWT_SECRET : .env.prod 값 (로그인 게이트용)
#   3) 공개 설정을 env 로 주입 (ALLOWED_HOSTS / AUTH_GATE / INVITE_GATE / SUPABASE_URL / SUPABASE_ANON_KEY)
#   4) gcloud run deploy --source . (Cloud Build가 Dockerfile로 빌드 → 배포)
#
# 실제 비밀은 .env.prod 에서만 읽으므로 스크립트엔 비밀이 박히지 않는다.
#
# 선행 1회 작업(스크립트 밖):
#   - gcloud config set project chajjaem-dev
#   - gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
#   - .env.prod 작성 (.env.prod.example 참고)
#   - 도메인 매핑: gongo.chajjaem.dev → gongo (Cloud Run 콘솔)
#   - Supabase: Google provider 활성화 + redirect URL 에 https://gongo.chajjaem.dev/login/ 등록
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

REGION="asia-northeast1"
SERVICE="gongo"
PROD_HOST="gongo.chajjaem.dev"
PYTHON=".venv/bin/python"

# ── .env.prod 로드 (공개 설정 + 비밀) ───────────────────────────────
SUPABASE_URL=""; SUPABASE_ANON_KEY=""; SUPABASE_JWT_SECRET=""
if [[ -f "$SCRIPT_DIR/.env.prod" ]]; then
  set -a; # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env.prod"; set +a
fi

# ── 1. 최신 스냅샷을 배포 아티팩트로 export ──────────────────────────
echo "[deploy] 최신 스냅샷 export..."
"$PYTHON" manage.py export_snapshot

# ── GCP 컴퓨트 SA (Secret 접근 권한 부여용) ─────────────────────────
project="$(gcloud config get-value project 2>/dev/null)"
project_number="$(gcloud projects describe "$project" --format='value(projectNumber)')"
COMPUTE_SA="${project_number}-compute@developer.gserviceaccount.com"

# 값을 Secret Manager 에 보장(생성/갱신) + SA accessor 부여
ensure_secret() {
  local name="$1" value="$2"
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    echo "[secrets] $name 생성"
    printf '%s' "$value" | gcloud secrets create "$name" \
      --data-file=- --replication-policy=automatic >/dev/null
  else
    local cur; cur=$(gcloud secrets versions access latest --secret="$name" 2>/dev/null || echo "")
    if [[ "$cur" != "$value" ]]; then
      echo "[secrets] $name 갱신 (값 변경 감지)"
      printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    fi
  fi
  gcloud secrets add-iam-policy-binding "$name" \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
}

# ── 2. 비밀값 동기화 ────────────────────────────────────────────────
# DJANGO_SECRET_KEY: 없으면 생성
if ! gcloud secrets describe gongo-django-secret-key >/dev/null 2>&1; then
  ensure_secret gongo-django-secret-key \
    "$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(50))')"
else
  gcloud secrets add-iam-policy-binding gongo-django-secret-key \
    --member="serviceAccount:$COMPUTE_SA" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
fi

SECRETS="DJANGO_SECRET_KEY=gongo-django-secret-key:latest"
if [[ -n "$SUPABASE_JWT_SECRET" ]]; then
  ensure_secret gongo-supabase-jwt-secret "$SUPABASE_JWT_SECRET"
  SECRETS+=",SUPABASE_JWT_SECRET=gongo-supabase-jwt-secret:latest"
fi

# ── 3. 공개 env 조립 (값에 쉼표가 있어 커스텀 구분자 ^@@^ 사용) ──────
ENV_PAIRS="ALLOWED_HOSTS=${PROD_HOST},.run.app@@AUTH_GATE=1@@INVITE_GATE=1"
[[ -n "$SUPABASE_URL" ]]      && ENV_PAIRS+="@@SUPABASE_URL=${SUPABASE_URL}"
[[ -n "$SUPABASE_ANON_KEY" ]] && ENV_PAIRS+="@@SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}"

# 로그인 게이트에 필수: SUPABASE_URL(JWKS 공개키 검증) + anon/publishable 공개키.
# SUPABASE_JWT_SECRET 은 선택 — 프로젝트가 비대칭(JWKS) 서명이면 불필요.
if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_ANON_KEY" ]]; then
  echo "[warn] SUPABASE_URL / SUPABASE_ANON_KEY 가 비어 있습니다."
  echo "       AUTH_GATE=1 상태에서는 로그인 불가로 사이트가 잠깁니다. .env.prod 를 확인하세요."
fi

# ── 4. Cloud Run 배포 ───────────────────────────────────────────────
echo "[deploy] $SERVICE → Cloud Run ($REGION)..."
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "^@@^${ENV_PAIRS}" \
  --set-secrets "$SECRETS"

echo ""
echo "[deploy] 완료. 검증:"
echo "  open https://${PROD_HOST}"
