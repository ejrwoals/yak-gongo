"""
팜리크루트(dailypharm) 스크래퍼.

사용 예:
    from scraper.pharm_recruit import scrape, CITY_URL_DICT

    postings = scrape(city_url_dict=CITY_URL_DICT['서울'], big_category='서울')
    # returns list[dict] — 각 dict는 JobPosting 생성에 필요한 raw 필드를 포함
"""
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PLATFORM = '팜리크루트'

_URLS_FILE = Path(__file__).parent / 'pharm_recruit_urls.json'

# city → list[url] 매핑. big_category 별로 그룹화.
# URL은 scraper/pharm_recruit_urls.json 에서 관리합니다.
with _URLS_FILE.open(encoding='utf-8') as _f:
    CITY_URL_DICT: dict[str, dict[str, list[str]]] = json.load(_f)


def _build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params['page'] = [str(page)]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


def scrape(
    big_category: str,
    year: int = 2026,
    headless: bool = False,
    existing_urls: set[str] | None = None,
    category_limit: int | None = None,
    log=None,
) -> list[dict]:
    """
    팜리크루트 공고를 순회하여 raw posting dict 리스트를 반환.

    Args:
        big_category:    수집할 지역 대분류 (CITY_URL_DICT의 키)
        headless:        헤드리스 모드 여부
        existing_urls:   이미 DB에 존재하는 URL 집합 (중복 스킵용)
        category_limit:  이 카테고리에서 수집할 최대 공고 수 (None = 전체)
                         내부적으로 도시 수로 나눠 균등 분배.
        year:            등록일 연도 (팜리크루트는 월/일만 표시되므로 별도 지정 필요)

    Returns:
        list of dict with keys:
            url, platform, created_at, title, pharmacy_name, body, city, big_category
    """
    if big_category not in CITY_URL_DICT:
        raise ValueError(f'지원하지 않는 big_category: {big_category}. 가능한 값: {list(CITY_URL_DICT)}')

    if existing_urls is None:
        existing_urls = set()

    _log = log or (lambda msg: print(msg))

    city_url_dict = CITY_URL_DICT[big_category]

    # 도시별 수집 한도: category_limit을 도시 수로 균등 분배 (올림)
    num_cities = len(city_url_dict)
    if category_limit is not None:
        city_limit = math.ceil(category_limit / num_cities)
        _log(f'[{big_category}] 도시 {num_cities}개 × 최대 {city_limit}개/도시 (카테고리 한도 {category_limit}개)')
    else:
        city_limit = None

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('headless')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1024, 768)

    results = []
    try:
        for city, url_list in city_url_dict.items():
            city_collected = 0
            city_done = False

            for base_url in url_list:
                if city_done:
                    break
                page = 0
                while True:
                    url = _build_page_url(base_url, page)
                    _log(f'페이지: {city} — page={page} — {url}')
                    driver.get(url)
                    driver.implicitly_wait(3)

                    found_on_page = 0
                    for n in range(1, 41):
                        try:
                            child_css = (
                                '#container > div.offer_wrap.contWidth.width100'
                                f' > ul > li:nth-child({n}) > div.tit_wrap > div.tit > a'
                            )
                            child = driver.find_element(By.CSS_SELECTOR, child_css)
                            child.click()
                            driver.implicitly_wait(3)

                            cur_url = driver.current_url
                            if cur_url in existing_urls:
                                driver.back()
                                driver.implicitly_wait(5)
                                found_on_page += 1
                                continue

                            name_css = (
                                '#container > div > div.view_wrap > div.viewCont_wrap.sideIdxTop'
                                ' > div.top_wrap > div.tit_wrap > div.company'
                            )
                            name = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, name_css))
                            ).text

                            title_css = (
                                '#container > div > div.view_wrap > div.viewCont_wrap.sideIdxTop'
                                ' > div.top_wrap > div.tit_wrap > div.tit'
                            )
                            title = driver.find_element(By.CSS_SELECTOR, title_css).text

                            date_css = (
                                '#container > div > div.view_wrap > div.viewCont_wrap.sideIdxTop'
                                ' > div.cont_wrap > div.contDiv.step.sideIdxTop'
                                ' > div.flexBox > div.flexL.date_wrap > div:nth-child(1) > span:nth-child(2)'
                            )
                            date_text = driver.find_element(By.CSS_SELECTOR, date_css).text
                            # date_text 형식: '03.14(토)'
                            month = date_text.split('.')[0].zfill(2)
                            day = date_text.split('.')[1].split('(')[0].zfill(2)
                            created_at = f'{year}-{month}-{day}'

                            body_css = (
                                '#container > div > div.view_wrap > div.viewCont_wrap.sideIdxTop'
                                ' > div.cont_wrap > div.contDiv.detail > div.ck-content'
                            )
                            body_text = driver.find_element(By.CSS_SELECTOR, body_css).text

                            body = f'공고제목 :{title}\n{body_text}'

                            results.append({
                                'url': cur_url,
                                'platform': PLATFORM,
                                'created_at': created_at,
                                'title': title,
                                'pharmacy_name': name,
                                'body': body,
                                'city': city,
                                'big_category': big_category,
                            })
                            city_collected += 1
                            found_on_page += 1
                            _log(f'  {city} - {n}번 글 수집 완료 ({city_collected}/{city_limit or "∞"}) | {title} | {name} | {cur_url}')

                            driver.back()
                            driver.implicitly_wait(5)

                            if city_limit is not None and city_collected >= city_limit:
                                city_done = True
                                break  # for n

                        except Exception:
                            # 공고 목록은 순차적이므로 첫 실패 = 이 페이지에 더 이상 공고 없음
                            break

                    if city_done or found_on_page == 0:
                        if found_on_page == 0:
                            _log(f'  {city} — page={page} 공고 없음, 다음 지역으로')
                        break  # while True

                    page += 1

    finally:
        driver.quit()

    return results
