from django.conf import settings


def supabase(request):
    """템플릿에서 Supabase 클라이언트를 초기화할 공개 설정을 노출한다.

    로컬(값 비어있음)에서는 템플릿의 인증 스크립트 블록이 렌더되지 않는다.
    anon key는 공개용이므로 클라이언트 JS에 노출해도 안전하다.
    """
    return {
        'SUPABASE_URL': settings.SUPABASE_URL,
        'SUPABASE_ANON_KEY': settings.SUPABASE_ANON_KEY,
    }
