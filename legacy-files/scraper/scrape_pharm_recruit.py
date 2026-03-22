big_category = '서울'

if big_category == '서울':
    city_url_dict = {
        '서울-강남구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=138&keyword='],
        '서울-강동구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=140&keyword='],
        '서울-강북구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=124&keyword='],
        '서울-강서구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=131&keyword='],
        '서울-관악구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=136&keyword='],
        '서울-광진구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=120&keyword='],
        '서울-구로구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=132&keyword='],
        '서울-금천구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=133&keyword='],
        '서울-노원구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=126&keyword='],
        '서울-도봉구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=125&keyword='],
        '서울-동대문구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=121&keyword='],
        '서울-동작구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=135&keyword='],
        '서울-마포구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=129&keyword='],
        '서울-서대문구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=128&keyword='],
        '서울-서초구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=137&keyword='],
        '서울-성동구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=119&keyword='],
        '서울-성북구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=123&keyword='],
        '서울-송파구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=139&keyword='],
        '서울-양천구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=130&keyword='],
        '서울-영등포구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=134&keyword='],
        '서울-용산구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=118&keyword='],
        '서울-은평구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=127&keyword='],
        '서울-종로구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=116&keyword='],
        '서울-중구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=117&keyword='],
        '서울-중랑구' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=122&keyword='],
    }
elif big_category == '인천':
    city_url_dict = {
        '인천' : ['http://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=100&keyword=',
                'http://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=100&keyword=',
                'https://recruit.dailypharm.com/Search.php?page=3&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=100&keyword='],
    }
elif big_category == '지방':
    city_url_dict = {
        '부산' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=98&keyword=',
                'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=98&keyword=',
                #'https://recruit.dailypharm.com/Search.php?page=3&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=98&keyword=',
                #'https://recruit.dailypharm.com/Search.php?page=4&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=98&keyword='
                ],
        '광주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=101&keyword=',
                'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=101&keyword='
                ],
        '대전' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=104&keyword='],
        '울산' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=105&keyword='],
        '세종' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=106&keyword='],
        '강원' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=108&keyword=',
                #'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=108&keyword='
                ],
        '충북' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=109&keyword='],
        '충남' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=110&keyword='],
        '전북' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=111&keyword='],
        '전남' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=112&keyword='],
        '경북' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=113&keyword='],
        '경남' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=114&keyword=',
                #'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=114&keyword='
                ],
        '제주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=115&keyword='],
    }
elif big_category == '경기 중부':  # 경기 중부 : 고양, 양주, 의정부, 남양주, 구리, 하남, 경기도광주, 성남, 과천, 의왕, 안양, 군포, 광명, 시흥, 부천, 김포
    city_url_dict = {
        '고양' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4344&optionAreaVal%5B%5D=221&optionAreaVal%5B%5D=222&optionAreaVal%5B%5D=223&keyword='],
        '양주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=229&keyword='],
        '의정부' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=224&keyword='],
        '남양주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=227&keyword='],
        '구리' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=226&keyword='],
        '하남 ' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=212&keyword='],
        '경기도광주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=217&keyword='],
        '성남' : ['https://recruit.dailypharm.com/Search.php?page=1&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4317&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=196&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=196&keyword=',
                #'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4317&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=196&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=196&optionAreaVal[]=197&optionAreaVal[]=195&optionAreaVal[]=196&optionAreaVal[]=196&keyword='
                ],
        '과천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=207&keyword='],
        '의왕' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=211&keyword='],
        '안양' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4336&optionAreaVal%5B%5D=199&optionAreaVal%5B%5D=198&keyword='],
        '군포' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=210&keyword='],
        '광명' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=205&keyword='],
        '시흥' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=209&keyword='],
        '부천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=219&optionAreaVal%5B%5D=4908&optionAreaVal%5B%5D=4901&optionAreaVal%5B%5D=1729&keyword='],
        '김포' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=215&keyword='],
    }
elif big_category == '경기 외곽':  # 경기 외곽 : 파주, 동두천, 연천, 포천, 가평, 양평, 여주, 이천, 안성, 용인, 평택, 오산, 화성, 수원, 안산
    city_url_dict = {
        '파주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=228&keyword='],
        '동두천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=225&keyword='],
        '연천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=231&keyword='],
        '포천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=230&keyword='],
        '가평' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=232&keyword='],
        '양평' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=220&keyword='],
        '여주' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=218&keyword='],
        '이천' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=213&keyword='],
        '안성' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=214&keyword='],
        '용인' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4338&optionAreaVal%5B%5D=203&optionAreaVal%5B%5D=204&optionAreaVal%5B%5D=202&keyword=',
                'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4338&optionAreaVal[]=203&optionAreaVal[]=204&optionAreaVal[]=202&optionAreaVal[]=203&optionAreaVal[]=204&optionAreaVal[]=202&keyword='],
        '평택' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=206&keyword='],
        '오산' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=208&keyword='],
        '화성' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=216&keyword='],
        '수원' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=4376&optionAreaVal%5B%5D=192&optionAreaVal%5B%5D=194&optionAreaVal%5B%5D=191&optionAreaVal%5B%5D=193&keyword=',
                'https://recruit.dailypharm.com/Search.php?page=2&mode=offer&GraduateLevel=&employ_id=&optionJobVal[]=12&optionJobVal[]=13&optionJobVal[]=4776&optionAreaVal[]=4376&optionAreaVal[]=192&optionAreaVal[]=194&optionAreaVal[]=191&optionAreaVal[]=193&optionAreaVal[]=192&optionAreaVal[]=194&optionAreaVal[]=191&optionAreaVal[]=193&keyword='
                ],
        '안산' : ['https://recruit.dailypharm.com/Search.php?mode=offer&GraduateLevel=&employ_id=&optionJobVal%5B%5D=12&optionJobVal%5B%5D=13&optionJobVal%5B%5D=4776&optionAreaVal%5B%5D=201&optionAreaVal%5B%5D=200&keyword='],
    }
else:
    print('잘못된 지역 입력')
    exit()

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
                        #  service=service  # 24-09-23 갑자기 무슨 이유에서인지 service를 쓰면 에러가 나서 일단 사용 중지해놨음..;
)
driver.set_window_size(1024, 768) # 너비와 높이를 설정합니다.

# CSV 파일로 내보내기 전에 일단 data_list에 담기
data_list = []

# 반복 시작
for city, url_list in city_url_dict.items():
    for url in url_list:
        print('페이지 링크 :', url)
        print('='*100)
        print((city + ' ')*20)
        print('='*100)
        driver.get(url)
        # 페이지 로딩이 완료될 때까지 최대 N초간 대기하는 함수 : implicityly_wait (-> https://mr-doosun.tistory.com/39 참고함)
        driver.implicitly_wait(3)

        #=================== 셀레니움 + 노션 + ChatGPT ================================#
        for n in range(1, 21):  # 페이지당 마지막 child 번호가 거의 40번까지이긴 함.
            try:
        #         date_css = '#container > div.searchPageWrap > div > div.search_tab.clearfix > ul > li:nth-child(%d) > a > div > div.search_tabCont_company > p.tabCont_date.tabCont_dateS'%n
        #         date_text = driver.find_element(By.CSS_SELECTOR, date_css).text
        #         print(date_text)

                child = driver.find_element(By.CSS_SELECTOR, '#container > div.searchPageWrap > div > div.search_tab.clearfix > ul > li:nth-child(%d) > a > div > div.search_tabCont_info.clearfix'%n)
                child.click()
                print(city, ' - ', n, '번 글')

                driver.implicitly_wait(3)

                cur_url = driver.current_url
                print(cur_url)

                # 약국 이름
                name_css = '#container > div.recruitView_wrap > div.firstView.OfferViewWarp > div.offer_title_wrap > h1'
                name = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, name_css))).text
                print(name)

                # 공고 제목
                title_css = '#container > div.recruitView_wrap > div.firstView.OfferViewWarp > div.offer_title_wrap > h2'
                title = driver.find_element(By.CSS_SELECTOR, title_css).text
                print(title)

                # 공고 등록일
                date_css = '#container > div.recruitView_wrap > div.secondView > div.secondViewbody > div.buttonSection > p'
                date = driver.find_element(By.CSS_SELECTOR, date_css).text  # date = '공고등록일 :2023년 03월 15일 14시 03 분'

                # 연, 월, 일 부분 추출
                year = date.split('년')[0].split()[-1][1:]
                month = date.split('월')[0].split()[-1].zfill(2)
                day = date.split('일')[1].split()[-1].zfill(2)
                date = f"{year}-{month}-{day}"
                print(date)

                # 페이지를 iframe으로 전환
                driver.switch_to.frame(0)  #iframe은 거의 보통 0번이라서 0을 넣음!
                time.sleep(1)

                # 본문
                body = driver.find_element(By.CSS_SELECTOR, 'html').text
                print(body)
                print('='*20)
                
                # 본문에 제목 합치기
                body = "공고제목 :" + title + '\n' + body
                
                # ==================== CSV 파일 만들기 for Llama-3 ============================ #
                data_dict = {
                    '링크': cur_url,
                    '등록일': date,
                    '공고 제목': title,
                    '약국 명칭': name,
                    '본문' : body,
                    '지역' : city,
                    '지역 대분류' : big_category,
                    '플랫폼' : '팜리크루트',        
                }
                
                data_list.append(data_dict)

                # back page로 복귀하기
                driver.back()
                driver.implicitly_wait(10)

            except Exception as e:
                print(city, ' - ', n, '번 글 없음')
                pass

# 종료
driver.close()

# CSV 파일로 데이터 내보내기
df = pd.DataFrame(data_list)
df.to_csv('output_{}.csv'.format(big_category), index=False, encoding='utf-8-sig')

print('\n\n총 데이터 개수 :', len(df))
print("\n======= CSV 파일 저장 완료! =======\n")