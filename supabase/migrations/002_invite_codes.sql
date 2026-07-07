-- 002_invite_codes.sql
-- 초대코드(allow-list) 기반 진입 게이트  (APP_ID = 'gongo')
-- Supabase SQL Editor에서 실행. 001_users_bootstrap.sql 이후.
--
-- 설계 요지:
--   - invite_codes: 관리자가 채워두는 allow-list. app 컬럼으로 앱별 분리.
--   - invite_claims: 어떤 유저가 어떤 코드/채널로 통과했는지 트래킹 로그.
--   - public.users에 invite_code/invited_channel 라벨 추가.
--   - claim_invite() RPC(SECURITY DEFINER)가 검증/부여를 전담 → allow-list는 DB 밖으로 안 나감.

-- ============================================================
-- 1. invite_codes (allow-list)
-- ============================================================

CREATE TABLE public.invite_codes (
    code       TEXT NOT NULL,                    -- 초대코드(대문자로 저장, 대소문자 무시)
    app        TEXT NOT NULL DEFAULT 'gongo',    -- 앱 식별자
    channel    TEXT NOT NULL,                    -- 마케팅 채널 라벨 ('instagram', 'kakao', ...)
    is_active  BOOLEAN NOT NULL DEFAULT true,    -- false면 즉시 비활성
    max_uses   INTEGER,                          -- NULL = 무제한, 숫자면 사용 상한
    used_count INTEGER NOT NULL DEFAULT 0,       -- 부여된 횟수(자동 증가)
    note       TEXT,                             -- 관리 메모
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, app),                     -- 같은 코드 문자열을 앱별로 재사용 가능
    -- 코드는 대문자로만 저장. 소문자 insert 시 즉시 에러 → claim 시점 무음 불일치 방지.
    CONSTRAINT invite_codes_code_upper CHECK (code = upper(code))
);

-- RLS 켜되 정책을 만들지 않음 = anon/authenticated 직접 접근 전면 차단.
-- 오직 service role(관리자)과 SECURITY DEFINER 함수만 접근 → allow-list 비노출.
ALTER TABLE public.invite_codes ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 2. invite_claims (트래킹 로그)
-- ============================================================

CREATE TABLE public.invite_claims (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app        TEXT NOT NULL,
    code       TEXT NOT NULL,
    channel    TEXT NOT NULL,
    user_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 마찬가지로 정책 없음 = 관리자/함수만 접근.
ALTER TABLE public.invite_claims ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_invite_claims_app_channel ON public.invite_claims(app, channel);

-- ============================================================
-- 3. public.users 라벨 컬럼
-- ============================================================

ALTER TABLE public.users
    ADD COLUMN invite_code       TEXT,          -- 이 유저가 통과한 코드
    ADD COLUMN invited_channel   TEXT,          -- 유입 채널 스냅샷(분석 편의)
    ADD COLUMN access_granted_at TIMESTAMPTZ;   -- 최초 통과 시각

-- ============================================================
-- 4. claim_invite() RPC
-- 로그인한 유저(auth.uid())가 호출. 검증 + 부여 + 트래킹을 원자적으로 처리.
-- 반환: { granted: bool, channel: text|null, reason: text|null }
-- ============================================================

CREATE OR REPLACE FUNCTION public.claim_invite(p_code TEXT, p_app TEXT DEFAULT 'gongo')
RETURNS JSONB AS $$
DECLARE
    v_uid      UUID := auth.uid();
    v_existing TEXT;
    v_existing_channel TEXT;
    v_channel  TEXT;
BEGIN
    IF v_uid IS NULL THEN
        RETURN jsonb_build_object('granted', false, 'channel', NULL, 'reason', 'unauthenticated');
    END IF;

    -- 대소문자 무시: 입력을 대문자로 정규화(코드는 대문자로 저장됨).
    p_code := upper(btrim(p_code));

    -- 이미 통과한 유저면 코드 재검증 없이 통과(멱등). 기기/브라우저 무관하게 재진입 허용.
    SELECT invite_code, invited_channel INTO v_existing, v_existing_channel
    FROM public.users WHERE id = v_uid;

    IF v_existing IS NOT NULL THEN
        RETURN jsonb_build_object('granted', true, 'channel', v_existing_channel, 'reason', 'already_granted');
    END IF;

    -- allow-list 검증: 활성 + 사용 상한 미초과.
    SELECT channel INTO v_channel
    FROM public.invite_codes
    WHERE code = p_code
      AND app = p_app
      AND is_active = true
      AND (max_uses IS NULL OR used_count < max_uses)
    FOR UPDATE;

    IF v_channel IS NULL THEN
        RETURN jsonb_build_object('granted', false, 'channel', NULL, 'reason', 'invalid');
    END IF;

    -- 부여: 유저 라벨링 + 사용 카운트 + 트래킹 로그.
    UPDATE public.users
    SET invite_code = p_code,
        invited_channel = v_channel,
        access_granted_at = now()
    WHERE id = v_uid;

    UPDATE public.invite_codes
    SET used_count = used_count + 1
    WHERE code = p_code AND app = p_app;

    INSERT INTO public.invite_claims (app, code, channel, user_id)
    VALUES (p_app, p_code, v_channel, v_uid);

    RETURN jsonb_build_object('granted', true, 'channel', v_channel, 'reason', 'claimed');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 로그인한 유저만 호출 가능하도록 실행 권한 부여.
REVOKE ALL ON FUNCTION public.claim_invite(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_invite(TEXT, TEXT) TO authenticated;

-- ============================================================
-- 5. (미래용) Supabase-served 데이터 테이블 RLS 게이트 패턴
-- ============================================================
-- gongo는 현재 대시보드 데이터를 Supabase가 아니라 번들 스냅샷 JSON(Django)에서
-- 서빙하므로, "코드 없는 유저의 데이터 접근 차단"의 실제 경계는 Django 미들웨어다
-- (web/middleware.py의 초대코드 확인). 따라서 지금은 EXISTS 조인을 걸 대상 테이블이 없다.
--
-- 나중에 Supabase가 직접 서빙하는 유저 데이터 테이블(예: public.reports)을 추가하면,
-- 그 테이블의 SELECT 정책 USING 절에 아래 조건을 반드시 넣어 코드 없는 유저(유효 JWT
-- 보유자 포함)의 PostgREST 직접 접근을 서버측에서 차단한다:
--
--   CREATE POLICY "invited users can read" ON public.reports FOR SELECT
--   USING (
--     EXISTS (
--       SELECT 1 FROM public.users u
--       WHERE u.id = auth.uid() AND u.invite_code IS NOT NULL
--     )
--   );
