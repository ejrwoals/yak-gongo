from django.apps import AppConfig


class PostingsConfig(AppConfig):
    name = 'postings'

    def ready(self):
        # 서버 재시작 시 비정상 종료된 'running' 레코드를 'failed'로 정리
        # connection_created 시그널을 사용해 첫 DB 연결 이후에 실행
        from django.db.backends.signals import connection_created

        def _cleanup_orphans(sender, connection, **kwargs):
            connection_created.disconnect(_cleanup_orphans)
            try:
                from postings.models import PipelineRun
                PipelineRun.objects.filter(status='running').update(status='failed')
            except Exception:
                pass

        connection_created.connect(_cleanup_orphans)
