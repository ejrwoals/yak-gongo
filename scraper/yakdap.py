"""
약문약답 스크래퍼.

사용 예:
    from scraper.yakdap import scrape

    postings = scrape(start_id=38800, count=100, step=2, year=2024)
    # returns list[dict] — 각 dict는 JobPosting 생성에 필요한 raw 필드를 포함
"""
import time
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PLATFORM = '약문약답'
BASE_URL = 'https://app.stg.ymyd.onjourney.co.kr/jobpost/view?id='
LOGIN_URL = 'https://app.stg.ymyd.onjourney.co.kr/main/boards'


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
    year: int = 2024,
    headless: bool = False,
    existing_urls: set[str] | None = None,
) -> list[dict]:
    """
    약문약답 공고를 순회하여 raw posting dict 리스트를 반환.

    Args:
        start_id:      탐색 시작 공고 ID
        count:         탐색할 공고 개수
        step:          ID 증가 간격 (K)
        year:          등록일 연도 (약문약답은 월/일만 표시됨)
        headless:      헤드리스 모드 여부
        existing_urls: 이미 DB에 존재하는 URL 집합 (중복 스킵용)

    Returns:
        list of dict with keys:
            url, platform, created_at, title, pharmacy_name, body, city
    """
    if existing_urls is None:
        existing_urls = set()

    driver = _build_driver(headless)
    try:
        driver.get(LOGIN_URL)
        input('카카오 로그인을 완료하였으면 Enter를 누르세요.')

        results = []
        for i in range(count):
            num_id = start_id + i * step
            cur_url = BASE_URL + str(num_id)

            if cur_url in existing_urls:
                print(f'{num_id} 번 글 - 중복 스킵')
                continue

            driver.get(cur_url)
            driver.implicitly_wait(3)

            try:
                title_css = '#app > ion-app > main > section.title-container > h1'
                title = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, title_css))
                ).text
                title = PLATFORM + ') ' + title

                name_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > div > h4'
                name = driver.find_element(By.CSS_SELECTOR, name_css).text

                address_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > span'
                address = driver.find_element(By.CSS_SELECTOR, address_css).text

                date_css = '#app > ion-app > main > section.title-container > div.detail-title__bottom > span'
                date_text = driver.find_element(By.CSS_SELECTOR, date_css).text
                month = date_text.split('월')[0].split()[-1].zfill(2)
                day = date_text.split('일')[0].split()[-1].zfill(2)
                created_at = f'{year}-{month}-{day}'

                salary_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(1) > td.sc-fTNIjK.jUdFRA > div > span'
                salary = driver.find_element(By.CSS_SELECTOR, salary_css).text

                work_hours_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(3) > td.sc-fTNIjK.jUdFRA > div'
                work_hours = driver.find_element(By.CSS_SELECTOR, work_hours_css).text

                body_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > pre'
                body_text = driver.find_element(By.CSS_SELECTOR, body_css).text

                body = (
                    f'공고 제목 : {title}\n'
                    f'약국 이름 : {name}\n'
                    f'약국 주소 : {address}\n'
                    f'근무 시간 : {work_hours}\n'
                    f'급여 : {salary}\n'
                    f'글 본문 : {body_text}'
                )

                results.append({
                    'url': cur_url,
                    'platform': PLATFORM,
                    'created_at': created_at,
                    'title': title,
                    'pharmacy_name': name,
                    'body': body,
                    'city': address,
                })
                print(f'{num_id} 번 글 수집 완료')

            except Exception as e:
                print(f'{num_id} 번 글 없음: {e}')

    finally:
        driver.quit()

    return results
