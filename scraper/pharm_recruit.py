"""
팜리크루트(dailypharm) 스크래퍼.

사용 예:
    from scraper.pharm_recruit import scrape, CITY_URL_DICT

    postings = scrape(city_url_dict=CITY_URL_DICT['서울'], big_category='서울')
    # returns list[dict] — 각 dict는 JobPosting 생성에 필요한 raw 필드를 포함
"""
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PLATFORM = '팜리크루트'

# city → list[url] 매핑. big_category 별로 그룹화.
CITY_URL_DICT: dict[str, dict[str, list[str]]] = {
    '서울': {
        '서울-강남구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=138&keyword='],
        '서울-강동구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=140&keyword='],
        '서울-강북구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=124&keyword='],
        '서울-강서구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=131&keyword='],
        '서울-관악구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=136&keyword='],
        '서울-광진구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=120&keyword='],
        '서울-구로구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=132&keyword='],
        '서울-금천구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=133&keyword='],
        '서울-노원구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=126&keyword='],
        '서울-도봉구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=125&keyword='],
        '서울-동대문구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=121&keyword='],
        '서울-동작구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=135&keyword='],
        '서울-마포구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=129&keyword='],
        '서울-서대문구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=128&keyword='],
        '서울-서초구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=137&keyword='],
        '서울-성동구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=119&keyword='],
        '서울-성북구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=123&keyword='],
        '서울-송파구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=139&keyword='],
        '서울-양천구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=130&keyword='],
        '서울-영등포구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=134&keyword='],
        '서울-용산구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=118&keyword='],
        '서울-은평구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=127&keyword='],
        '서울-종로구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=116&keyword='],
        '서울-중구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=117&keyword='],
        '서울-중랑구': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=122&keyword='],
    },
    '인천': {
        '인천': [
            'http://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=100&keyword=',
            'http://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=100&keyword=',
            'https://recruit.dailypharm.com/Search.php?page=3&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=100&keyword=',
        ],
    },
    '지방': {
        '부산': [
            'https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=98&keyword=',
            'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=98&keyword=',
        ],
        '광주': [
            'https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=101&keyword=',
            'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=101&keyword=',
        ],
        '대전': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=104&keyword='],
        '울산': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=105&keyword='],
        '세종': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=106&keyword='],
        '강원': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=108&keyword='],
        '충북': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=109&keyword='],
        '충남': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=110&keyword='],
        '전북': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=111&keyword='],
        '전남': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=112&keyword='],
        '경북': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=113&keyword='],
        '경남': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=114&keyword='],
        '제주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=115&keyword='],
    },
    '경기 중부': {
        '고양': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4344&optionAreaVal%5B%5D=221&optionAreaVal%5B%5D=222&optionAreaVal%5B%5D=223&keyword='],
        '양주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=229&keyword='],
        '의정부': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=224&keyword='],
        '남양주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=227&keyword='],
        '구리': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=226&keyword='],
        '하남': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=212&keyword='],
        '경기도광주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=217&keyword='],
        '성남': ['https://recruit.dailypharm.com/Search.php?page=1&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4317&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&keyword='],
        '과천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=207&keyword='],
        '의왕': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=211&keyword='],
        '안양': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4336&optionAreaVal%5B%5D=199&optionAreaVal%5B%5D=198&keyword='],
        '군포': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=210&keyword='],
        '광명': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=205&keyword='],
        '시흥': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=209&keyword='],
        '부천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=219&optionAreaVal%5B%5D=4908&optionAreaVal%5B%5D=4901&optionAreaVal%5B%5D=1729&keyword='],
        '김포': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=215&keyword='],
    },
    '경기 외곽': {
        '파주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=228&keyword='],
        '동두천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=225&keyword='],
        '연천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=231&keyword='],
        '포천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=230&keyword='],
        '가평': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=232&keyword='],
        '양평': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=220&keyword='],
        '여주': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=218&keyword='],
        '이천': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=213&keyword='],
        '안성': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=214&keyword='],
        '용인': [
            'https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4338&optionAreaVal%5B%5D=203&optionAreaVal%5B%5D=204&optionAreaVal%5B%5D=202&keyword=',
            'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4338&optionAreaVal[]=203&optionAreaVal[]=204&optionAreaVal[]=202&keyword=',
        ],
        '평택': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=206&keyword='],
        '오산': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=208&keyword='],
        '화성': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=216&keyword='],
        '수원': [
            'https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4376&optionAreaVal%5B%5D=192&optionAreaVal%5B%5D=194&optionAreaVal%5B%5D=191&optionAreaVal%5B%5D=193&keyword=',
            'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4376&optionAreaVal[]=192&optionAreaVal[]=194&optionAreaVal[]=191&optionAreaVal[]=193&keyword=',
        ],
        '안산': ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=201&optionAreaVal%5B%5D=200&keyword='],
    },
}


def scrape(
    big_category: str,
    headless: bool = False,
    existing_urls: set[str] | None = None,
) -> list[dict]:
    """
    팜리크루트 공고를 순회하여 raw posting dict 리스트를 반환.

    Args:
        big_category:  수집할 지역 대분류 (CITY_URL_DICT의 키)
        headless:      헤드리스 모드 여부
        existing_urls: 이미 DB에 존재하는 URL 집합 (중복 스킵용)

    Returns:
        list of dict with keys:
            url, platform, created_at, title, pharmacy_name, body, city, big_category
    """
    if big_category not in CITY_URL_DICT:
        raise ValueError(f'지원하지 않는 big_category: {big_category}. 가능한 값: {list(CITY_URL_DICT)}')

    if existing_urls is None:
        existing_urls = set()

    city_url_dict = CITY_URL_DICT[big_category]

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('headless')
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1024, 768)

    results = []
    try:
        for city, url_list in city_url_dict.items():
            for url in url_list:
                print(f'페이지: {city} — {url}')
                driver.get(url)
                driver.implicitly_wait(3)

                for n in range(1, 41):
                    try:
                        child_css = (
                            '#container > div.searchPageWrap > div > div.search_tab.clearfix'
                            f' > ul > li:nth-child({n}) > a > div > div.search_tabCont_info.clearfix'
                        )
                        child = driver.find_element(By.CSS_SELECTOR, child_css)
                        child.click()
                        driver.implicitly_wait(3)

                        cur_url = driver.current_url
                        if cur_url in existing_urls:
                            driver.back()
                            driver.implicitly_wait(5)
                            continue

                        name_css = '#container > div.recruitView_wrap > div.firstView.OfferViewWarp > div.offer_title_wrap > h1'
                        name = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, name_css))
                        ).text

                        title_css = '#container > div.recruitView_wrap > div.firstView.OfferViewWarp > div.offer_title_wrap > h2'
                        title = driver.find_element(By.CSS_SELECTOR, title_css).text

                        date_css = '#container > div.recruitView_wrap > div.secondView > div.secondViewbody > div.buttonSection > p'
                        date_text = driver.find_element(By.CSS_SELECTOR, date_css).text
                        year = date_text.split('년')[0].split()[-1][1:]
                        month = date_text.split('월')[0].split()[-1].zfill(2)
                        day = date_text.split('일')[1].split()[-1].zfill(2)
                        created_at = f'{year}-{month}-{day}'

                        driver.switch_to.frame(0)
                        time.sleep(1)
                        body_text = driver.find_element(By.CSS_SELECTOR, 'html').text
                        driver.switch_to.default_content()

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
                        print(f'  {city} - {n}번 글 수집 완료')

                        driver.back()
                        driver.implicitly_wait(5)

                    except Exception as e:
                        print(f'  {city} - {n}번 글 없음: {e}')
                        try:
                            driver.switch_to.default_content()
                            driver.back()
                            driver.implicitly_wait(5)
                        except Exception:
                            pass
    finally:
        driver.quit()

    return results
