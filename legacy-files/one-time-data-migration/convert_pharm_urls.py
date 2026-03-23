"""
팜리크루트 URL 일괄 변환 스크립트.

구 URL 형식(Search.php?optionAreaVal[]=...)을
신 URL 형식(Main/search.php?SearchData=<base64 JSON>...)으로 변환하여
pharm_recruit_urls.json을 새로 생성합니다.

실행:
    python scraper/convert_pharm_urls.py
"""
import base64
import json
import urllib.parse
from pathlib import Path

BASE_URL = 'https://recruit.dailypharm.com/Main/search.php'

MAIN_OFFER_TYPE = {
    "type": "checkbox",
    "cate": "MainOfferType",
    "nav": "OfferType",
    "mainname": "약국",
    "subname": "직무형태 전체",
    "value": "1",
    "id": "MainOfferType_1",
    "class": "chkInput MainOfferType",
}


def encode_search_data(data: list[dict]) -> str:
    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    b64 = base64.b64encode(json_str.encode('utf-8')).decode('ascii')
    return urllib.parse.quote(b64)


def seoul_district_urls(subname: str, value: int, pages: int = 1) -> list[str]:
    """서울 구 단위 — [MainOfferType, SubArea] 패턴 (parents_value=97)"""
    data = [
        MAIN_OFFER_TYPE,
        {
            "type": "checkbox",
            "id": f"SubArea_{value}",
            "cate": "SubArea",
            "nav": "Area",
            "mainname": "서울",
            "subname": subname,
            "value": str(value),
            "parents_id": "AllAreaType_97",
            "parents_cate": "MainArea",
            "parents_value": "97",
            "class": "chkInput SubArea",
        },
    ]
    sd = encode_search_data(data)
    return [f"{BASE_URL}?page={p}&CateNum=1&SearchData={sd}&OrderBy=&SearchKey=" for p in range(pages)]


def gyeonggi_city_urls(subname: str, value: int, pages: int = 1) -> list[str]:
    """경기 시/군 단위 — [MainOfferType, SubArea] 패턴 (parents_value=107)"""
    data = [
        MAIN_OFFER_TYPE,
        {
            "type": "checkbox",
            "id": f"SubArea_{value}",
            "cate": "SubArea",
            "nav": "Area",
            "mainname": "경기",
            "subname": subname,
            "value": str(value),
            "parents_id": "AllAreaType_107",
            "parents_cate": "MainArea",
            "parents_value": "107",
            "class": "chkInput SubArea",
        },
    ]
    sd = encode_search_data(data)
    return [f"{BASE_URL}?page={p}&CateNum=1&SearchData={sd}&OrderBy=&SearchKey=" for p in range(pages)]


def gyeonggi_multi_subarea_urls(areas: list[tuple[str, int]], pages: int = 1) -> list[str]:
    """경기 복수 구 단위 — [MainOfferType, SubArea, SubArea, ...] 패턴"""
    data = [MAIN_OFFER_TYPE] + [
        {
            "type": "checkbox",
            "id": f"SubArea_{value}",
            "cate": "SubArea",
            "nav": "Area",
            "mainname": "경기",
            "subname": subname,
            "value": str(value),
            "parents_id": "AllAreaType_107",
            "parents_cate": "MainArea",
            "parents_value": "107",
            "class": "chkInput SubArea",
        }
        for subname, value in areas
    ]
    sd = encode_search_data(data)
    return [f"{BASE_URL}?page={p}&CateNum=1&SearchData={sd}&OrderBy=&SearchKey=" for p in range(pages)]


def metro_city_urls(mainname: str, value: int, pages: int = 1) -> list[str]:
    """광역시/도 단위 — [MainOfferType, AllArea] 패턴"""
    data = [
        MAIN_OFFER_TYPE,
        {
            "type": "checkbox",
            "cate": "MainArea",
            "nav": "Area",
            "mainname": mainname,
            "subname": "전체",
            "value": str(value),
            "id": f"AllAreaType_{value}",
            "class": "chkInput AllArea",
        },
    ]
    sd = encode_search_data(data)
    return [f"{BASE_URL}?page={p}&CateNum=1&SearchData={sd}&OrderBy=&SearchKey=" for p in range(pages)]


# ────────────────────────────────────────────────────────────────────────────
# 지역 데이터 정의
# (subname, area_value, pages)
# pages: 구 URL의 페이지 수와 동일하게 유지 (구 page=1 → 신 page=0, etc.)
# ────────────────────────────────────────────────────────────────────────────

SEOUL_DISTRICTS = {
    '서울-강남구': ('강남구', 138),
    '서울-강동구': ('강동구', 140),
    '서울-강북구': ('강북구', 124),
    '서울-강서구': ('강서구', 131),
    '서울-관악구': ('관악구', 136),
    '서울-광진구': ('광진구', 120),
    '서울-구로구': ('구로구', 132),
    '서울-금천구': ('금천구', 133),
    '서울-노원구': ('노원구', 126),
    '서울-도봉구': ('도봉구', 125),
    '서울-동대문구': ('동대문구', 121),
    '서울-동작구': ('동작구', 135),
    '서울-마포구': ('마포구', 129),
    '서울-서대문구': ('서대문구', 128),
    '서울-서초구': ('서초구', 137),
    '서울-성동구': ('성동구', 119),
    '서울-성북구': ('성북구', 123),
    '서울-송파구': ('송파구', 139),
    '서울-양천구': ('양천구', 130),
    '서울-영등포구': ('영등포구', 134),
    '서울-용산구': ('용산구', 118),
    '서울-은평구': ('은평구', 127),
    '서울-종로구': ('종로구', 116),
    '서울-중구': ('중구', 117),
    '서울-중랑구': ('중랑구', 122),
}

# (subname, area_value, pages) — 단일 SubArea 경기 시/군
# 복수 area ID였던 시는 4000번대 대표 ID 사용 (고양=4344, 성남=4317, 등)
GYEONGGI_CITIES = {
    '경기 중부': {
        '고양':    ('고양시',   4344, 1),
        '양주':    ('양주시',    229, 1),
        '의정부':  ('의정부시',  224, 1),
        '남양주':  ('남양주시',  227, 1),
        '구리':    ('구리시',    226, 1),
        '하남':    ('하남시',    212, 1),
        '경기도광주': ('광주시', 217, 1),
        '성남':    ('성남시',   4317, 1),
        '과천':    ('과천시',    207, 1),
        '의왕':    ('의왕시',    211, 1),
        '안양':    ('안양시',   4336, 1),
        '군포':    ('군포시',    210, 1),
        '광명':    ('광명시',    205, 1),
        '시흥':    ('시흥시',    209, 1),
        '부천':    ('부천시',    219, 1),
        '김포':    ('김포시',    215, 1),
    },
    '경기 외곽': {
        '파주':  ('파주시',   228, 1),
        '동두천': ('동두천시', 225, 1),
        '연천':  ('연천군',   231, 1),
        '포천':  ('포천시',   230, 1),
        '가평':  ('가평군',   232, 1),
        '양평':  ('양평군',   220, 1),
        '여주':  ('여주시',   218, 1),
        '이천':  ('이천시',   213, 1),
        '안성':  ('안성시',   214, 1),
        '용인':  ('용인시',  4338, 1),
        '평택':  ('평택시',   206, 1),
        '오산':  ('오산시',   208, 1),
        '화성':  ('화성시',   216, 1),
        '수원':  ('수원시',  4376, 1),
    },
}

# 복수 SubArea를 하나의 URL에 담는 경우: [(subname, value), ...]
GYEONGGI_MULTI = {
    '경기 외곽': {
        # 안산: 단원구(201) + 상록구(200) — 시 전체 ID 없음
        '안산': ([('안산시 단원구', 201), ('안산시 상록구', 200)], 1),
    },
}

# (mainname, area_value, pages)
METRO_CITIES = {
    '인천': {
        '인천': ('인천', 100, 1),
    },
    '지방': {
        '부산': ('부산', 98,  1),
        '광주': ('광주', 101, 1),
        '대전': ('대전', 104, 1),
        '울산': ('울산', 105, 1),
        '세종': ('세종', 106, 1),
        '강원': ('강원', 108, 1),
        '충북': ('충북', 109, 1),
        '충남': ('충남', 110, 1),
        '전북': ('전북', 111, 1),
        '전남': ('전남', 112, 1),
        '경북': ('경북', 113, 1),
        '경남': ('경남', 114, 1),
        '제주': ('제주', 115, 1),
    },
}


def build() -> dict:
    result = {}

    # 서울
    result['서울'] = {
        city: seoul_district_urls(subname, value)
        for city, (subname, value) in SEOUL_DISTRICTS.items()
    }

    # 인천 + 지방
    for big_cat, cities in METRO_CITIES.items():
        result[big_cat] = {
            city: metro_city_urls(mainname, value, pages)
            for city, (mainname, value, pages) in cities.items()
        }

    # 경기 중부 + 경기 외곽
    for big_cat, cities in GYEONGGI_CITIES.items():
        result[big_cat] = {
            city: gyeonggi_city_urls(subname, value, pages)
            for city, (subname, value, pages) in cities.items()
        }
        for city, (areas, pages) in GYEONGGI_MULTI.get(big_cat, {}).items():
            result[big_cat][city] = gyeonggi_multi_subarea_urls(areas, pages)

    return result


if __name__ == '__main__':
    out_path = Path(__file__).parent / 'pharm_recruit_urls.json'
    data = build()
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✓ {out_path} 업데이트 완료')
    for big_cat, cities in data.items():
        print(f'  [{big_cat}] {len(cities)}개 도시')
