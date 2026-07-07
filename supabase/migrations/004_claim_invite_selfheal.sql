-- 004_claim_invite_selfheal.sql
-- 버그 수정: 부트스트랩(001) 트리거/백필 이전에 가입한 유저는 public.users 행이 없어
-- claim_invite의 UPDATE ... WHERE id = v_uid 가 0행을 갱신(no-op)하는데도 granted:true를
-- 반환했다 → 서버 미들웨어가 invite_code를 못 보고 /login 으로 무한 반송.
--
-- 두 가지를 한다:
--   1) 이미 가입해 있으나 public.users 행이 없는 유저 백필(멱등).
--   2) claim_invite 를 self-healing 으로 교체 — 부여 직전 유저 행 존재를 보장한다.
-- Supabase SQL Editor에서 실행.

-- ── 1. 누락된 유저 행 백필 (auth.users → public.users) ─────────────
INSERT INTO public.users (id, display_name)
SELECT id, COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name')
FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- ── 2. claim_invite 교체 (유저 행 자기 치유) ──────────────────────
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

    -- 유저 행 보장(자기 치유): 부트스트랩 트리거/백필 이전에 가입한 유저는 행이 없을 수 있다.
    -- 없으면 여기서 만들어 아래 UPDATE 가 no-op 되는 것을 막는다. (SECURITY DEFINER → auth.users 조회 가능)
    INSERT INTO public.users (id, display_name)
    VALUES (
        v_uid,
        (SELECT COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name')
         FROM auth.users WHERE id = v_uid)
    )
    ON CONFLICT (id) DO NOTHING;

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

REVOKE ALL ON FUNCTION public.claim_invite(TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_invite(TEXT, TEXT) TO authenticated;
