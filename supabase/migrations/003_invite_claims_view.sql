-- 003_invite_claims_view.sql
-- invite_claims 조회용 뷰: user_id 옆에 이메일/닉네임을 붙여 참고하기 쉽게.
-- Supabase SQL Editor에서 실행. (앱 식별자 치환 불필요 — 뷰는 app 컬럼으로 필터)
--
-- 원본 invite_claims에는 user_id만 저장(중복 없음). 이메일은 auth.users,
-- 닉네임은 public.users에서 조인해 항상 최신값으로 보여줌.

CREATE OR REPLACE VIEW public.invite_claims_detailed AS
SELECT
    ic.id,
    ic.app,
    ic.code,
    ic.channel,
    ic.user_id,
    au.email,
    pu.display_name,
    ic.claimed_at
FROM public.invite_claims ic
LEFT JOIN auth.users   au ON au.id = ic.user_id
LEFT JOIN public.users pu ON pu.id = ic.user_id;

-- 관리자 전용. 이메일이 PostgREST(anon/authenticated)로 노출되지 않도록 차단.
-- 대시보드/서비스 롤은 이 REVOKE와 무관하게 조회 가능.
REVOKE ALL ON public.invite_claims_detailed FROM anon, authenticated;
