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

    # ── pharm_recruit 전용 ────────────────────────────────────────
    BIG_CATEGORY_CHOICES = [
        ('서울', '서울'),
        ('인천', '인천'),
        ('지방', '지방'),
        ('경기 중부', '경기 중부'),
        ('경기 외곽', '경기 외곽'),
    ]
    big_categories = forms.MultipleChoiceField(
        choices=BIG_CATEGORY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='지역 (대분류)',
    )
    pharm_count = forms.IntegerField(
        required=False, label='수집 개수',
        help_text='비워두면 전체 수집. 설정 시 선택 지역·도시 별로 균등 분배.',
        min_value=1,
    )

    # ── 공통 ─────────────────────────────────────────────────────
    year = forms.IntegerField(
        required=False, initial=2026, label='연도',
        help_text='등록일 연도 (팜리크루트·약문약답은 월/일만 표시됨)',
    )
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
            kwargs['year'] = data.get('year') or 2026
        else:
            kwargs['big_categories'] = data.get('big_categories') or ['서울']
            kwargs['pharm_count'] = data.get('pharm_count') or None
            kwargs['year'] = data.get('year') or 2026
        return kwargs
