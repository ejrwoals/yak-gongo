"""
약문약답 스크래퍼.

사용 예:
    from scraper.yakdap import scrape

    postings = scrape(start_id=38800, count=100, step=2, year=2024)
    # returns list[dict] — 각 dict는 JobPosting 생성에 필요한 raw 필드를 포함
"""
import time
import re
import threading
from datetime import date, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PLATFORM = '약문약답'
BASE_URL = 'https://app.stg.ymyd.onjourney.co.kr/jobpost/view?id='
LOGIN_URL = 'https://app.stg.ymyd.onjourney.co.kr/main/boards'


def _parse_created_at(date_text: str, fallback_year: int, today: date | None = None) -> str:
    """약문약답 등록일 텍스트를 'YYYY-MM-DD' 문자열로 변환한다.

    약문약답이 실제로 쓰는 등록일 형태:
      - 절대형: '2024년 11월 22일 오후 12:54' (오래된 공고. 연도 없이 '11월 22일'인 경우도 있음)
      - 어제:   '어제 오전 8:17'
      - 오늘:   날짜 키워드 없이 시각만('오전 8:36'), 또는 'N시간 전'·'N분 전'
    절대형은 그대로 파싱하고(연도 없으면 fallback_year 사용), 어제는 today-1, 그 외는 today로 본다.
    """
    text = date_text.strip()
    today = today or date.today()

    # 절대형: '...년 ...월 ...일' (연도는 선택)
    m = re.search(r'(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if m:
        y = int(m.group(1)) if m.group(1) else fallback_year
        return f'{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

    if text.startswith('어제'):
        return (today - timedelta(days=1)).isoformat()

    # 시각만('오전 8:36')·'N시간 전'·'N분 전' → 오늘
    return today.isoformat()


def _build_driver(headless: bool = False) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('headless')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1024, 768)
    return driver


def scrape(
    start_id: int,
    count: int = 100,
    step: int = 2,
    year: int | None = None,
    headless: bool = False,
    existing_urls: set[str] | None = None,
    login_event: threading.Event | None = None,
    log=None,
    on_item=None,
    on_error=None,
) -> list[dict]:
    """
    약문약답 공고를 순회하여 raw posting dict 리스트를 반환.

    Args:
        start_id:      탐색 시작 공고 ID
        count:         탐색할 공고 개수
        step:          ID 증가 간격 (K)
        year:          연도 폴백값 (약문약답은 공고에 적힌 연도를 우선 사용. None이면 현재 연도)
        headless:      헤드리스 모드 여부
        existing_urls: 이미 DB에 존재하는 URL 집합 (중복 스킵용)
        on_item:       공고 1건을 수집할 때마다 호출되는 콜백(dict). 중간 저장용.
        on_error:      공고 1건 수집이 실패할 때마다 호출되는 콜백(item_id, exc). 에러 집계용.

    Returns:
        list of dict with keys:
            url, platform, created_at, title, pharmacy_name, body, city
    """
    if existing_urls is None:
        existing_urls = set()
    if year is None:
        year = date.today().year

    _log = log or (lambda msg: print(msg))

    driver = _build_driver(headless)
    try:
        driver.get(LOGIN_URL)
        if login_event is not None:
            _log('[로그인 대기] 카카오 로그인 후 "로그인 완료" 버튼을 눌러주세요.')
            login_event.wait()
            _log('[로그인 완료] 스크래핑을 시작합니다.')
        else:
            input('카카오 로그인을 완료하였으면 Enter를 누르세요.')

        # 로그인 후 세션 초기화를 위해 메인 페이지 한 번 로드
        driver.get(LOGIN_URL)
        time.sleep(2)

        results = []
        for i in range(count):
            num_id = start_id + i * step
            cur_url = BASE_URL + str(num_id)

            if cur_url in existing_urls:
                _log(f'{num_id} 번 글 - 중복 스킵')
                continue

            driver.get(cur_url)
            time.sleep(1)

            try:
                # 사이트가 styled-components 해시 클래스(sc-*)를 쓰므로 재배포 시 클래스가 바뀐다.
                # 따라서 바뀌지 않는 시맨틱 클래스(title-container, detail__*)와
                # 표는 라벨 텍스트(XPath)를 기준으로 선택한다.
                title = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'main section.title-container h1'))
                ).text
                title = PLATFORM + ') ' + title

                name = driver.find_element(
                    By.CSS_SELECTOR, 'main .detail__pharmacy-name h4').text

                address = driver.find_element(
                    By.CSS_SELECTOR, 'main .detail__pharmacy-address').text

                date_text = driver.find_element(
                    By.CSS_SELECTOR, 'main section.title-container .detail-title__bottom > span').text
                # 절대형('2024년 11월 22일')·상대형('어제 오전 8:17') 모두 처리. year는 연도 없는 절대형의 폴백.
                created_at = _parse_created_at(date_text, year)

                # 급여·근무시간: 표의 라벨 셀 텍스트로 같은 행의 값 셀(td[2])을 찾는다.
                # 급여 셀에는 "세후 급여 계산하기" 버튼이 함께 들어 있어 .text에 섞이므로 제거한다.
                salary = driver.find_element(
                    By.XPATH, '//main//tr[td/span[normalize-space(text())="급여"]]/td[2]').text
                salary = salary.replace('세후 급여 계산하기', '').strip()
                work_hours = driver.find_element(
                    By.XPATH, '//main//tr[td/span[normalize-space(text())="근무시간"]]/td[2]').text

                body_text = driver.find_element(
                    By.CSS_SELECTOR, 'main .detail__message').text.strip()

                lines = [
                    f'공고 제목 : {title}',
                    f'약국 이름 : {name}',
                    f'약국 주소 : {address}',
                    f'근무 시간 : {work_hours}',
                    f'급여 : {salary}',
                ]
                # 작성자 자유 메시지(.detail__message)는 비어 있을 때가 많아, 있을 때만 넣는다.
                if body_text:
                    lines.append(f'글 본문 : {body_text}')
                body = '\n'.join(lines)

                record = {
                    'url': cur_url,
                    'platform': PLATFORM,
                    'created_at': created_at,
                    'title': title,
                    'pharmacy_name': name,
                    'body': body,
                    'city': address,
                }
                if on_item is not None:
                    on_item(record)
                results.append(record)
                _log(f'{num_id} 번 글 수집 완료 | {title} | {name} | {address} | {cur_url}')

            except Exception as e:
                _log(f'{num_id} 번 글 수집 실패: {e}')
                if on_error is not None:
                    on_error(num_id, e)

    finally:
        driver.quit()

    return results
