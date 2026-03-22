#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import json
import numpy as np

def csv_to_json(csv_file_path, json_file_path):
    """
    CSV 파일을 JSON 파일로 변환
    - 개행문자를 띄어쓰기로 대체
    - NULL 값은 null로 유지
    """
    
    # CSV 파일 읽기 (UTF-8 BOM 처리)
    df = pd.read_csv(csv_file_path, encoding='utf-8-sig')
    
    # 개행문자 처리: \n, \r을 띄어쓰기로 대체
    for col in df.columns:
        if df[col].dtype == 'object':  # 문자열 컬럼만 처리
            df[col] = df[col].astype(str).str.replace('\n', ' ', regex=False)
            df[col] = df[col].astype(str).str.replace('\r', ' ', regex=False)
            # 'nan' 문자열을 다시 NaN으로 변환 (원래 null 값 복원)
            df[col] = df[col].replace('nan', np.nan)
    
    # DataFrame을 딕셔너리 리스트로 변환
    records = df.to_dict('records')
    
    # JSON 파일로 저장 (한글 처리, 들여쓰기 적용)
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    print(f"변환 완료:")
    print(f"   입력: {csv_file_path}")
    print(f"   출력: {json_file_path}")
    print(f"   총 레코드 수: {len(records)}")

if __name__ == "__main__":
    csv_file = "/Users/mac_mini_jjaem/Desktop/yak-gongo/data/output_error.csv"
    json_file = "/Users/mac_mini_jjaem/Desktop/yak-gongo/data/output_error.json"
    
    csv_to_json(csv_file, json_file)