#!/usr/bin/env python3
import pandas as pd
import numpy as np
import sys
from pathlib import Path

def analyze_csv_structure(file_path):
    """Analyze CSV file structure and report findings"""
    print(f"=== CSV 파일 구조 분석: {file_path} ===\n")
    
    try:
        # Read CSV file
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        
        print(f"📊 기본 정보:")
        print(f"   - 총 행 수: {len(df):,}")
        print(f"   - 총 열 수: {len(df.columns)}")
        print(f"   - 파일 크기: {Path(file_path).stat().st_size / 1024 / 1024:.2f} MB\n")
        
        print(f"📋 컬럼 목록:")
        for i, col in enumerate(df.columns, 1):
            print(f"   {i:2d}. {col}")
        print()
        
        print(f"📏 각 컬럼별 텍스트 길이 분석:")
        print(f"{'컬럼명':<30} {'최대길이':>8} {'평균길이':>8} {'null개수':>8} {'null비율':>8}")
        print("-" * 70)
        
        for col in df.columns:
            # Convert to string and calculate lengths
            text_lengths = df[col].astype(str).str.len()
            max_length = text_lengths.max()
            avg_length = text_lengths.mean()
            null_count = df[col].isnull().sum()
            null_ratio = (null_count / len(df)) * 100
            
            col_display = col[:29] if len(col) > 29 else col
            print(f"{col_display:<30} {max_length:>8} {avg_length:>8.1f} {null_count:>8} {null_ratio:>7.1f}%")
        
        print(f"\n🔍 데이터 품질 검사:")
        
        # Check for completely empty rows
        empty_rows = df.isnull().all(axis=1).sum()
        print(f"   - 완전히 빈 행: {empty_rows}")
        
        # Check for rows with mostly null values (>80% null)
        mostly_null_rows = (df.isnull().sum(axis=1) > len(df.columns) * 0.8).sum()
        print(f"   - 대부분 null인 행 (80% 이상): {mostly_null_rows}")
        
        # Check for duplicate rows
        duplicate_rows = df.duplicated().sum()
        print(f"   - 중복 행: {duplicate_rows}")
        
        # Check for potential CSV parsing issues
        print(f"\n⚠️  잠재적 CSV 형식 문제:")
        
        # Check for newlines in text fields
        newline_issues = 0
        for col in df.columns:
            if df[col].dtype == 'object':  # String columns
                has_newlines = df[col].astype(str).str.contains('\n', na=False).sum()
                if has_newlines > 0:
                    newline_issues += has_newlines
                    print(f"   - '{col}' 컬럼에서 개행문자 포함 셀: {has_newlines}개")
        
        if newline_issues == 0:
            print("   - 개행문자 관련 문제 없음")
        
        # Sample data preview
        print(f"\n📖 데이터 샘플 (처음 3행):")
        for i in range(min(3, len(df))):
            print(f"\n--- 행 {i+1} ---")
            for col in df.columns:
                value = df.iloc[i][col]
                if pd.isna(value):
                    display_value = "[NULL]"
                else:
                    str_value = str(value)
                    display_value = str_value[:100] + "..." if len(str_value) > 100 else str_value
                print(f"  {col}: {display_value}")
        
        return df
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return None

if __name__ == "__main__":
    csv_file = "/Users/mac_mini_jjaem/Desktop/yak-gongo/data/yakkook.csv"
    # csv_file = "/Users/mac_mini_jjaem/Desktop/yak-gongo/data/output_error.csv"
    analyze_csv_structure(csv_file)