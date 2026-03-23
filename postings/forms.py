from django import forms


class PipelineRunForm(forms.Form):
    SOURCE_CHOICES = [
        ('yakdap', '약문약답 (yakdap)'),
        ('pharm_recruit', '팜리크루트 (pharm_recruit)'),
    ]

    source = forms.ChoiceField(
        choices=SOURCE_CHOICES,
        label='소스',
        widget=forms.RadioSelect,
    )

    # ── yakdap 전용 ───────────────────────────────────────────────
    start_id = forms.IntegerField(
        required=False, initial=38800, label='시작 ID',
        help_text='수집을 시작할 공고 ID',
    )
    count = forms.IntegerField(
        required=False, initial=100, label='수집 개수',
    )
    step = forms.IntegerField(
        required=False, initial=2, label='스텝 (ID 증가 간격)',
    )
    year = forms.IntegerField(
        required=False, initial=2024, label='연도',
    )

    # ── pharm_recruit 전용 ────────────────────────────────────────
    big_category = forms.CharField(
        required=False, initial='서울', label='지역 (대분류)',
        help_text='예: 서울, 경기 중부, 인천',
    )

    # ── 공통 ─────────────────────────────────────────────────────
    headless = forms.BooleanField(
        required=False, initial=True, label='헤드리스 모드',
        help_text='브라우저 창 없이 실행 (서버 환경 권장)',
    )
    dry_run = forms.BooleanField(
        required=False, label='Dry Run',
        help_text='스크래핑만 하고 LLM 처리 및 DB 저장은 건너뜁니다.',
    )

    def get_command_kwargs(self) -> dict:
        """form 데이터를 run_pipeline management command 인자 형태로 변환."""
        data = self.cleaned_data
        source = data['source']
        kwargs = {
            'source': source,
            'headless': data.get('headless', True),
            'dry_run': data.get('dry_run', False),
        }
        if source == 'yakdap':
            kwargs['headless'] = False  # 카카오 로그인 필요
            kwargs['start_id'] = data.get('start_id') or 38800
            kwargs['count'] = data.get('count') or 100
            kwargs['step'] = data.get('step') or 2
            kwargs['year'] = data.get('year') or 2024
        else:
            kwargs['big_category'] = data.get('big_category') or '서울'
        return kwargs
