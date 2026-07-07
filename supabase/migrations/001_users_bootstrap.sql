-- 001_users_bootstrap.sql
-- gongo(얼마줄약) 전용 Supabase 프로젝트에는 아직 public.users가 없다
-- (기존 게이트는 JWT만 검증하고 public.users를 조회하지 않았음).
-- 초대코드 게이트를 붙이려면 auth.users와 동기화되는 public.users가 필요하다.
-- Supabase SQL Editor에서 002 "이전에" 실행한다.
--
-- 하는 일: auth.users와 동기화되는 public.users를 만들고, 가입 시 자동 생성 트리거를 건다.
-- 말해보약 001_initial_schema.sql의 검증된 정의를 그대로 옮긴 것.

CREATE TABLE public.users (
    id           UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own data"
    ON public.users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own data"
    ON public.users FOR UPDATE
    USING (auth.uid() = id);

-- auth.users → public.users 자동 동기화 트리거
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, display_name)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 참고: 이 마이그레이션 이전에 이미 가입한 유저(auth.users에는 있으나 public.users에는 없는)를
-- 백필하려면 아래를 한 번 실행한다. 신규 프로젝트라 유저가 없으면 생략해도 무방.
INSERT INTO public.users (id, display_name)
SELECT id, COALESCE(raw_user_meta_data->>'full_name', raw_user_meta_data->>'name')
FROM auth.users
ON CONFLICT (id) DO NOTHING;
