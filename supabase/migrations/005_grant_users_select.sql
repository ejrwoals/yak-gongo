-- 005_grant_users_select.sql
-- 버그 수정: public.users 에 authenticated 롤의 테이블 SELECT 권한이 없어 PostgREST 조회가
-- 403 Forbidden. Supabase에서 RLS는 GRANT 위에 얹히는 계층이라 정책(policy)만으로는 부족하고
-- GRANT SELECT 도 있어야 읽힌다. (대시보드로 만든 테이블은 자동 GRANT되지만, SQL로 직접
-- CREATE TABLE 한 경우 이 auto-grant가 안 걸릴 수 있다.)
--
-- 증상: claim_invite(SECURITY DEFINER)는 권한 무관하게 부여에 성공해 users.invite_code 가 찍히지만,
-- 클라이언트 sb.from('users') 조회와 서버 미들웨어의 invite_code 확인이 둘 다 403으로 막혀
-- 부여된 유저조차 /login 으로 무한 반송됐다.
--
-- 안전성: RLS "Users can read own data"(auth.uid() = id) 정책이 자기 행으로 제한하므로,
-- SELECT 권한을 줘도 유저는 남의 행을 못 본다. invite_codes/invite_claims 는 여전히 GRANT 없이
-- 잠겨 있어(allow-list 비노출) 그대로 둔다.
-- Supabase SQL Editor에서 실행. 재배포 불필요.

GRANT SELECT ON public.users TO authenticated;
