from django.test import TestCase

from pipeline.salary import calculate_net_salary, ceil_hourly_wage
from postings import review_agent as ra
from postings.models import JobPosting


class AgentEditableFieldsTests(TestCase):
    """파생 필드는 agent 편집 대상에서 빠지고, 기반 입력값은 남아 있어야 한다."""

    def test_derived_fields_not_editable(self):
        for f in ra.AGENT_DERIVED_FIELDS:
            self.assertNotIn(f, ra._EDITABLE_SET, f'{f} 는 편집 불가여야 함')

    def test_base_inputs_still_editable(self):
        for f in ('net_salary', 'weekend_start_time', 'is_one_time_work'):
            self.assertIn(f, ra._EDITABLE_SET)

    def test_derived_fields_still_visible(self):
        """패널·스냅샷에는 파생 필드도 (자동계산 표시로) 노출돼야 한다."""
        for f in ra.AGENT_DERIVED_FIELDS:
            self.assertIn(f, ra.AGENT_VISIBLE_FIELDS)


class PretaxConversionTests(TestCase):
    """net_salary_pretax(세전 월급) 가상 필드는 파이프라인 공식으로 net_salary 로 환산된다."""

    def test_pretax_field_converts_to_net_salary(self):
        out = ra._normalize_updates([{'field': 'net_salary_pretax', 'value': '250'}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['field'], 'net_salary')
        self.assertEqual(float(out[0]['value']), round(calculate_net_salary(250), 2))

    def test_non_numeric_pretax_is_dropped(self):
        self.assertEqual(ra._normalize_updates([{'field': 'net_salary_pretax', 'value': 'x'}]), [])

    def test_other_fields_pass_through(self):
        ups = [{'field': 'weekend_work_days', 'value': '1'}]
        self.assertEqual(ra._normalize_updates(ups), ups)

    def test_apply_update_with_pretax(self):
        p = JobPosting.objects.create(url='https://example.com/pt', is_one_time_work=False)
        applied = ra.apply_update(p, [{'field': 'net_salary_pretax', 'value': '250'}])
        p.refresh_from_db()
        self.assertAlmostEqual(p.net_salary, round(calculate_net_salary(250), 2))
        self.assertTrue(any(a['field'] == 'net_salary' for a in applied))

    def test_response_schema_shape(self):
        """구조화 출력 스키마는 message + updates 를 요구한다(function-calling 미사용)."""
        schema = ra._response_schema()
        self.assertEqual(set(schema.properties), {'message', 'updates'})
        self.assertFalse(hasattr(ra, '_tool'))  # function-calling 도구 제거됨


class RecomputeDerivedTests(TestCase):
    """recompute_derived 가 파이프라인 공식대로 파생 필드를 채운다(LLM 손계산 드리프트 제거)."""

    def test_weekend_schedule_drift_fixed(self):
        # 관찰된 케이스: 매주 토 8:30~14:30(6h), 세후 월급 108.86.
        # LLM 은 hours_per_month=26.09 로 어긋났으나, 시스템은 6×4.34=26.04 로 정확해야 한다.
        p = JobPosting(
            weekend_start_time=8.5, weekend_end_time=14.5, weekend_work_days=1,
            net_salary=108.86, is_one_time_work=False,
        )
        ra.recompute_derived(p)
        self.assertEqual(p.hours_per_week, 6.0)
        self.assertAlmostEqual(p.hours_per_month, 26.04)
        self.assertEqual(p.net_hourly_wage, ceil_hourly_wage(108.86 / 26.04))

    def test_weekday_plus_weekend_summed(self):
        p = JobPosting(
            weekday_start_time=9.0, weekday_end_time=18.0, weekday_work_days=5,
            weekend_start_time=9.0, weekend_end_time=13.0, weekend_work_days=1,
            net_salary=300.0, is_one_time_work=False,
        )
        ra.recompute_derived(p)
        self.assertEqual(p.hours_per_week, 5 * 9 + 1 * 4)  # 49

    def test_one_time_work_leaves_net_hourly_untouched(self):
        """일회성 근무는 net_hourly_wage(지속성 전용)를 계산하지 않는다."""
        p = JobPosting(
            weekend_start_time=8.5, weekend_end_time=14.5, weekend_work_days=1,
            net_salary=100.0, is_one_time_work=True, net_hourly_wage=None,
        )
        ra.recompute_derived(p)
        self.assertIsNone(p.net_hourly_wage)

    def test_no_schedule_keeps_existing_hours(self):
        """일정 단서가 없으면 기존 hours_per_week 를 덮어쓰지 않는다."""
        p = JobPosting(hours_per_week=20.0, net_salary=None, is_one_time_work=False)
        ra.recompute_derived(p)
        self.assertEqual(p.hours_per_week, 20.0)


class ApplyUpdateRecomputeTests(TestCase):
    """승인 반영(apply_update) 직후 파생 필드가 auto 변경분으로 함께 적용된다."""

    def test_schedule_edit_triggers_auto_recompute(self):
        p = JobPosting.objects.create(
            url='https://example.com/p1',
            net_salary=108.86, is_one_time_work=False,
        )
        applied = ra.apply_update(p, [
            {'field': 'weekend_start_time', 'value': '8.5'},
            {'field': 'weekend_end_time', 'value': '14.5'},
            {'field': 'weekend_work_days', 'value': '1'},
        ])
        p.refresh_from_db()
        self.assertAlmostEqual(p.hours_per_month, 26.04)
        auto = {a['field'] for a in applied if a.get('auto')}
        self.assertIn('hours_per_month', auto)
        self.assertIn('hours_per_week', auto)

    def test_derived_field_proposal_is_ignored(self):
        """모델이 파생 필드를 직접 제안해도 편집 불가라 반영되지 않는다."""
        p = JobPosting.objects.create(
            url='https://example.com/p2', hours_per_month=10.0,
        )
        applied = ra.apply_update(p, [
            {'field': 'hours_per_month', 'value': '999'},
        ])
        p.refresh_from_db()
        self.assertNotEqual(p.hours_per_month, 999)
        self.assertFalse(any(a['field'] == 'hours_per_month' and not a.get('auto') for a in applied))
