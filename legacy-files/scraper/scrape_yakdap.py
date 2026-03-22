platform = '약문약답'
start_url_id = 38800  # 시작할 url 의 'https://app.stg.ymyd.onjourney.co.kr/jobpost/view?id=' 부분 뒤에 오는 숫자
NUM = 100  # 총 몇개의 공고를 탐색할 것인지?
K = 2    # K개마다 1개씩 공고를 띄엄띄엄 서치함. (같은 날짜의 공고를 너무 많이 샘플링하는 것 같아서 좀 띄엄띄엄해도 될듯 )
year = 2024 # 약문약답은 등록일에 년도가 생략되어 있어서 내가 직접 넣어줘야 함

# 24년5월13일 기준 start_url_id = 27300 까지 완료함.
# 24년7월11일 기준 url_id = 27500 ~ 30990 까지 완료함.
# 24년7월13일 기준 31680 번 글이 가장 최신글이라 거기까지만 뽑힘. 며칠 지난 후에 31500 ~ 31990 공고 다시 뽑아야할듯
# 24년7월14일 기준 27501 ~ 31491 까지 완료함
# 24년9월23일 - 노션 중복검사 코드 없앴음.
# 24년9월23일 기준 31501 ~ 32991 & 31500 ~ 32990 까지 완료함.
# 24년10월4일 기준 33000 ~ 34491 까지 완료함.
# 24년10월11일 기준 34500 ~ 35991 까지 완료함. 
# 24년10월13일 기준 36000 ~ 36491 까지 완료함. (10월11일 기준, 가장 최근 글이 36500번대임)
# 24년10월13일 기준 2번대 처음 시작. 34002 ~ 36492 완료.
# 24년10월27일 기준 36500 ~ 36990 까지 완료함. (10월27일 기준, 가장 최근 글이 37300번대임)
# 24년11월25일 기준 37000 ~ 38490 까지 완료함. (11월25일 기준, 가장 최근 글이 38850번대임)
# 24년11월26일 기준 36501 ~ 38491 까지 완료함.
# 24년12월3일 기준 38500 ~ 38998 까지 완료함. 2씩 건너 뛰면서 샘플링 (12월3일 기준, 가장 최근 글이 39330번대임)

#================== 셀레니움 =======================================#
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from webdriver_manager.chrome import ChromeDriverManager # 웹드라이브 매니저를 쓰면 크롬 버전을 자동적으로 match시켜주는듯
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
import time
import re
import pprint
import pandas as pd

# headless 옵션
# service = Service(ChromeDriverManager().install()) # 참고 : https://pypi.org/project/webdriver-manager/
webdriver_options = webdriver.ChromeOptions()
#webdriver_options.add_argument('headless')

# 사이트 접속
driver = webdriver.Chrome(options=webdriver_options,
                         #service=service  # 24-09-23 갑자기 무슨 이유에서인지 service를 쓰면 에러가 나서 일단 사용 중지해놨음..;
)
driver.set_window_size(1024, 768) # 너비와 높이를 설정합니다.

yakmunyakdap_url = 'https://app.stg.ymyd.onjourney.co.kr/main/boards'
driver.get(yakmunyakdap_url)
check_point = input('카카오 로그인을 완료하였으면 Enter를 누르세요.')

base_url = 'https://app.stg.ymyd.onjourney.co.kr/jobpost/view?id='
start_url = base_url + str(start_url_id)
driver.get(start_url)

# CSV 파일로 내보내기 전에 일단 data_list에 담기
data_list = []

# 반복 시작
for i in range( NUM ): # 0부터 NUM 까지
    num_id = start_url_id + i*K  # id를 K씩 증가시키면서 공고를 탐색
    cur_url = base_url + str(num_id)
    print(num_id, '번 글')
    
    driver.get(cur_url)
    # 페이지 로딩이 완료될 때까지 최대 N초간 대기하는 함수 : implicityly_wait (-> https://mr-doosun.tistory.com/39 참고함)
    driver.implicitly_wait(3)

    #=================== 셀레니움 + ChatGPT ================================#
    try:
        # 공고 제목
        title_css = '#app > ion-app > main > section.title-container > h1'
        title = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, title_css))).text
        title = platform + ') ' + title
        print(title)

        # 약국 이름
        # name_css = '#app > ion-app > main > section.sc-cuWdqJ.eujbm > div > h4'
        name_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > div > h4'  # 24-09-23 css selector가 변경되어서 새로 다 설정해 줌;;
        name = driver.find_element(By.CSS_SELECTOR, name_css).text
        print(name)

        # 약국 주소
        # address_css = '#app > ion-app > main > section.sc-cuWdqJ.eujbm > span'
        address_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > span'
        address = driver.find_element(By.CSS_SELECTOR, address_css).text
        print(address)

        # 공고 등록일
        date_css = '#app > ion-app > main > section.title-container > div.detail-title__bottom > span'
        date = driver.find_element(By.CSS_SELECTOR, date_css).text  # date = '3월 15일 오후 14:03'

        # 연, 월, 일 부분 추출
        month = date.split('월')[0].split()[-1].zfill(2)
        day = date.split('일')[0].split()[-1].zfill(2)
        date = f"{year}-{month}-{day}"
        print(date)

        # 급여
        # salary_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(1) > td.sc-hRxcUd.iOTvwA > div > span'
        salary_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(1) > td.sc-fTNIjK.jUdFRA > div > span'
        salary = driver.find_element(By.CSS_SELECTOR, salary_css).text
        print(salary)

        # 근무요일
        # work_days_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(2) > td.sc-hRxcUd.iOTvwA > div > span'
        work_days_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(2) > td.sc-fTNIjK.jUdFRA > div > span'
        work_days = driver.find_element(By.CSS_SELECTOR, work_days_css).text
        print(work_days)

        # 근무 시간
        # work_hours_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(3) > td.sc-hRxcUd.iOTvwA > div'
        work_hours_css = '#app > ion-app > main > section:nth-child(2) > table > tbody > tr:nth-child(3) > td.sc-fTNIjK.jUdFRA > div'
        work_hours = driver.find_element(By.CSS_SELECTOR, work_hours_css).text
        print(work_hours)

        # 페이지를 iframe으로 전환
#         driver.switch_to.frame(0)  #iframe은 거의 보통 0번이라서 0을 넣음!
#         time.sleep(1)

        # 본문
        # body_css = '#app > ion-app > main > section.sc-cuWdqJ.eujbm > pre'
        body_css = '#app > ion-app > main > section.sc-fTACoA.ktVljS > pre'
        body = driver.find_element(By.CSS_SELECTOR, body_css).text
        print(body)
        print('='*20)
        
        # 본문에 디테일 정보 합치기
        body = "공고 제목 : " + title + "\n약국 이름 : " + name + "\n약국 주소 : " + address + "\n근무 시간 : " + work_hours + "\n급여 : " + salary + "\n글 본문 : " + body

        # ==================== CSV 파일 만들기 for Llama-3 ============================ #
        # To Do
        # - city랑 big_category를 어떻게 해결할지
        # - LLM 돌려서 임베딩 뽑아서 유사한거 서치
        
        data_dict = {
            '링크': cur_url,
            '등록일': date,
            '공고 제목': title,
            '약국 명칭': name,
            '본문' : body,
            '지역' : address, # 원래 city가 들어가야 하지만 약문약답에는 address 밖에 없으므로 일단 address로 뽑음
            '지역 대분류' : address, # big_category도 일단 address로 뽑은뒤 추후 LLM으로 처리할 예정.
            '플랫폼' : '약문약답',        
        }

        data_list.append(data_dict)

    except Exception as e:
        print(num_id, '번 글 없음')
        print(e)
        pass

# 종료
driver.close()

# CSV 파일로 데이터 내보내기
df = pd.DataFrame(data_list)
df.to_csv('output_YakDap_id({}~{}).csv'.format(start_url_id, num_id), index=False, encoding='utf-8-sig')

print('\n\n총 데이터 개수 :', len(df))
print("\n======= CSV 파일 저장 완료! =======\n")