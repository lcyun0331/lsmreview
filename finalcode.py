import pandas as pd
import csv
import json
import os
from flask import Flask, render_template, jsonify

# --- 경로 설정: 스크립트 실행 위치와 관계없이 파일 찾기 ---
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Jupyter/Colab 환경 등에서 __file__이 정의되지 않은 경우
    BASE_DIR = os.getcwd()

CSV_FILE = os.path.join(BASE_DIR, "finalreviewdata.csv")
JSON_FILE = os.path.join(BASE_DIR, "review_data.json")


# ---------------------------------------------------
# 1) 깨진 CSV 자동 복구용 로더 (인코딩/구분자 오류 처리 강화)
# ---------------------------------------------------
def load_broken_csv(path):
    # 인코딩 리스트 (순서: 흔한 utf-8-sig -> cp949 -> euc-kr)
    encodings = ["utf-8-sig", "cp949", "euc-kr"] 
    separators = [",", ";", "\t"] # 쉼표, 세미콜론, 탭 구분자를 순차적으로 시도
    
    df = None
    success = False
    
    print(f"CSV 파일 '{os.path.basename(path)}' 로드 시도 중...")

    # 인코딩과 구분자 조합으로 포괄적 시도
    for encoding in encodings:
        for sep in separators:
            try:
                fixed_rows = []
                
                # errors='ignore'를 open 함수에 적용하여 UnicodeDecodeError 방지
                with open(path, "r", encoding=encoding, errors='ignore') as f:
                    reader = csv.reader(f, delimiter=sep) # 지정된 구분자 사용

                    # 첫 행(컬럼명)을 읽어내고, header로 저장하지 않습니다.
                    header = next(reader, None)
                    if not header: continue

                    for row in reader:
                        if not row: continue 
                            
                        # 사용자 정의 쉼표 문제 복구 로직 (8개 컬럼 기준)
                        if len(row) == 8:
                            fixed_rows.append(row)
                        elif len(row) > 8:
                            # Review 안에서 쉼표 때문에 컬럼이 깨진 경우
                            no = row[0]
                            last_cols = row[-6:]
                            review_parts = row[1:len(row)-6]
                            review = ",".join(review_parts)
                            new_row = [no, review] + last_cols
                            fixed_rows.append(new_row)
                        # else: 컬럼 수가 8개 미만인 경우는 무시 (데이터 유효성 낮다고 가정)

                # DataFrame으로 변환
                df = pd.DataFrame(fixed_rows, columns=[
                    "No", "Review", "Length", "LSM_Score",
                    "Category", "Product", "Expertise", "Priority"
                ])
                
                # 유효성 검증: Category 컬럼에 데이터가 성공적으로 로드되었는지 확인
                if len(df) > 10 and df["Category"].notna().sum() > 0: 
                    print(f"CSV 로드 성공! (인코딩: {encoding}, 구분자: '{sep}')")
                    success = True
                    break
            except Exception as e:
                # print(f"인코딩 '{encoding}', 구분자 '{sep}' 시도 실패: {e}") # 디버깅용
                continue
        if success:
            break

    if not success or df is None:
        raise Exception(f"오류: 모든 인코딩 및 구분자 조합으로도 CSV 파일 '{os.path.basename(path)}'을 로드할 수 없습니다.")

    # 숫자형 변환 (로드 성공 시 실행)
    df["Length"] = pd.to_numeric(df["Length"], errors="coerce")
    df["LSM_Score"] = pd.to_numeric(df["LSM_Score"], errors="coerce")
    df["Priority"] = pd.to_numeric(df["Priority"], errors="coerce")

    return df


# ---------------------------------------------------
# 2) 데이터 전처리 → JSON 변환
# ---------------------------------------------------
def preprocess():
    try:
        df = load_broken_csv(CSV_FILE)
    except Exception as e:
        print(f"데이터 로드 치명적 실패: {e}")
        return {}
    
    print(f"CSV 로드 완료! 총 {len(df)}행")

    df["Product"] = df["Product"].str.strip()
    df["Category"] = df["Category"].str.strip()

    df_sorted = df.sort_values(by="Priority", ascending=False)

    out = {}
    for cat, cg in df_sorted.groupby("Category"):
        prod_dict = {}
        for prod, pg in cg.groupby("Product"):
            top10 = pg.head(10).to_dict(orient="records")
            prod_dict[prod] = top10
        out[cat] = prod_dict

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)

    print("JSON 저장 완료")
    return out


# ---------------------------------------------------
# 3) Flask 서버
# ---------------------------------------------------
REVIEW_DATA = preprocess()

app = Flask(__name__)

@app.route("/")
def index():
    # REVIEW_DATA가 비어있으면 (데이터 로드 실패 시) 빈 리스트를 전달
    categories = list(REVIEW_DATA.keys())
    return render_template("index.html", categories=categories)

@app.route("/api/data")
def get_data():
    return jsonify(REVIEW_DATA)


if __name__ == "__main__":
    app.run(debug=True)