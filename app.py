import math
import pandas as pd
import requests
import streamlit as st

# 1. 페이지 설정
st.set_page_config(page_title="배송 경로 최적화 & 배차 대시보드", layout="wide")

st.title("🚚 배송 경로 최적화 & 배차 대시보드")
st.caption(
    "출발지: 경기도 용인시 당하로 159 | 차량 기준: 1톤(최대 70대 적재) |"
    " 카카오모빌리티 도로망 API 연동"
)

# --- 사이드바 설정 및 API Key 입력 ---
st.sidebar.header("🔑 API 설정")
kakao_api_key = st.sidebar.text_input(
    "Kakao REST API Key",
    type="password",
    help="카카오 디벨로퍼스에서 발급받은 REST API 키를 입력하세요.",
)

st.sidebar.header("📁 데이터 업로드")
uploaded_file = st.sidebar.file_uploader(
    "자료샘플.xlsx 파일을 업로드하세요", type=["xlsx"]
)

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
else:
    # 자료샘플.xlsx 기반 예시 데이터셋
    data = [
        {
            "거래처명": "해병대교육훈련단",
            "배송지주소": (
                "인천시 남동구 청능대로 336 대림시스템 / 오전배송요청 /"
                " 도착 전 전화요청"
            ),
            "받는사람": "유진수",
            "전화번호": "010-8699-5323",
            "품목": "A3TC-5NBDN-AG003",
            "요청수량": 47,
            "요청담당자명": "이성훈",
        },
        {
            "거래처명": "경상북도교육청 경상북도영천교육지원청",
            "배송지주소": "경북 영천시 금호읍 관정1길 31 거여초등학교",
            "받는사람": "이례정보기술",
            "전화번호": "010-2563-1190",
            "품목": "A4TC-5NBDN-AH004",
            "요청수량": 16,
            "요청담당자명": "류주현",
        },
        {
            "거래처명": "경상북도교육청 경상북도영천교육지원청",
            "배송지주소": "경북 영천시 금호읍 금호로 179 금호초등학교",
            "받는사람": "이례정보기술",
            "전화번호": "010-2563-1190",
            "품목": "A4TC-5NBDN-AH004",
            "요청수량": 31,
            "요청담당자명": "류주현",
        },
        {
            "거래처명": "세명대학교",
            "배송지주소": "충북 제천시 용두대로304",
            "받는사람": "최명수",
            "전화번호": "010-5485-0486",
            "품목": "A4SC-5NBDN-AH002",
            "요청수량": 19,
            "요청담당자명": "강정호",
        },
        {
            "거래처명": "경기도구리남양주교육청 내양초등학교",
            "배송지주소": "경기 구리시 동구릉로 485 내양초등학교 1층 행정실",
            "받는사람": "이현주",
            "전화번호": "031-571-6669",
            "품목": "A4SC-4NBDF-AH004",
            "요청수량": 1,
            "요청담당자명": "변현준",
        },
        {
            "거래처명": "광주광역시 동구청",
            "배송지주소": "전남광주통합특별시 동구 서남로 1",
            "받는사람": "이승철",
            "전화번호": "010-5640-0007",
            "품목": "A4TC-5NBDN-AH000",
            "요청수량": 32,
            "요청담당자명": "윤가은",
        },
    ]
    df = pd.DataFrame(data)

# 필수 컬럼 기본값 처리 (업로드 파일에 없을 경우 예외 방지)
for col in ["받는사람", "전화번호", "요청담당자명"]:
    if col not in df.columns:
        df[col] = "-"

# --- 출발지 설정 ---
START_ADDRESS = "경기도 용인시 당하로 159"


# --- 2. 카카오 API 함수 정의 ---
@st.cache_data
def get_coordinates(address, api_key):
    if not api_key:
        return None, None
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": address}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            docs = res.json().get("documents")
            if docs:
                return float(docs[0]["x"]), float(docs[0]["y"])
    except Exception:
        pass
    return None, None


@st.cache_data
def get_kakao_route_info(origin_coord, dest_coord, api_key):
    if not api_key or None in origin_coord or None in dest_coord:
        return float("inf"), 0

    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {
        "origin": f"{origin_coord[0]},{origin_coord[1]}",
        "destination": f"{dest_coord[0]},{dest_coord[1]}",
        "priority": "RECOMMEND",
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            summary = res.json()["routes"][0]["summary"]
            distance_km = round(summary["distance"] / 1000.0, 1)
            duration_min = round(summary["duration"] / 60.0, 1)
            return distance_km, duration_min
    except Exception:
        pass
    return float("inf"), 0


start_lng, start_lat = get_coordinates(START_ADDRESS, kakao_api_key)


# --- 3. 권역 구분 함수 ---
def get_region(addr):
    addr_str = str(addr)
    if "서울" in addr_str:
        return "수도권(서울)"
    elif "인천" in addr_str:
        return "수도권(인천)"
    elif "경기" in addr_str:
        return "수도권(경기)"
    elif "충북" in addr_str or "충청북도" in addr_str:
        return "충청권(충북)"
    elif (
        "충남" in addr_str
        or "충청남도" in addr_str
        or "대전" in addr_str
        or "세종" in addr_str
    ):
        return "충청권(충남/대전)"
    elif (
        "전북" in addr_str
        or "전북특별자치도" in addr_str
        or "전라북도" in addr_str
    ):
        return "호남권(전북)"
    elif "전남" in addr_str or "전라남도" in addr_str or "광주" in addr_str:
        return "호남권(전남/광주)"
    elif "경북" in addr_str or "경상북도" in addr_str or "대구" in addr_str:
        return "영남권(경북/대구)"
    elif (
        "경남" in addr_str
        or "경상남도" in addr_str
        or "부산" in addr_str
        or "울산" in addr_str
    ):
        return "영남권(경남/부산)"
    elif "강원" in addr_str:
        return "강원권"
    else:
        return "기타권역"


df["권역"] = df["배송지주소"].apply(get_region)

# --- 4. 실제 도로망 기반 이동거리 및 이동시간 산출 ---
if kakao_api_key:
    coords_list = [
        get_coordinates(addr, kakao_api_key) for addr in df["배송지주소"]
    ]
    df["경도"] = [c[0] for c in coords_list]
    df["위도"] = [c[1] for c in coords_list]

    route_results = [
        get_kakao_route_info(
            (start_lng, start_lat), (row["경도"], row["위도"]), kakao_api_key
        )
        for _, row in df.iterrows()
    ]
    df["도로망거리_km"] = [r[0] for r in route_results]
    df["이동시간_분"] = [r[1] for r in route_results]

    df = df.sort_values(by=["도로망거리_km", "배송지주소"]).reset_index(
        drop=True
    )
    st.sidebar.success("✅ 카카오 도로망 API 연동 완료")
else:
    region_proximity_order = [
        "수도권(경기)",
        "수도권(서울)",
        "수도권(인천)",
        "충청권(충북)",
        "충청권(충남/대전)",
        "강원권",
        "호남권(전북)",
        "호남권(전남/광주)",
        "영남권(경북/대구)",
        "영남권(경남/부산)",
        "기타권역",
    ]
    df["권역우선순위"] = df["권역"].apply(
        lambda x: (
            region_proximity_order.index(x)
            if x in region_proximity_order
            else 99
        )
    )
    df["도로망거리_km"] = 0.0
    df["이동시간_분"] = 0.0
    df = df.sort_values(by=["권역우선순위", "배송지주소"]).reset_index(
        drop=True
    )
    st.sidebar.warning(
        "⚠️ API Key 미입력: 기존 행정구역 우선순위로 정렬됩니다."
    )

# --- 5. 차량 배차 및 경유 순서 정렬 ---
vehicle_counter = 1
dispatch_dict = {}

for region, group in df.groupby("권역", sort=False):
    current_truck_qty = 0
    current_truck_num = None

    address_groups = group.groupby("배송지주소", sort=False)

    for addr, addr_df in address_groups:
        addr_qty = addr_df["요청수량"].sum()

        if addr_qty > 70:
            trucks_needed = math.ceil(addr_qty / 70)
            v_list = [
                f"차량 {vehicle_counter + i:02d}" for i in range(trucks_needed)
            ]
            vehicle_counter += trucks_needed
            v_str = f"[단독배차] {region} ({addr_qty}대 / 1톤 {','.join(v_list)})"
            for idx in addr_df.index:
                dispatch_dict[idx] = v_str
        else:
            if current_truck_num is None or (
                current_truck_qty + addr_qty > 70
            ):
                current_truck_num = f"차량 {vehicle_counter:02d}"
                vehicle_counter += 1
                current_truck_qty = addr_qty
            else:
                current_truck_qty += addr_qty

            v_str = f"{region} 경유배차 - {current_truck_num}"
            for idx in addr_df.index:
                dispatch_dict[idx] = v_str

df["배차계획"] = df.index.map(dispatch_dict)

# 경유 순서 부여
seq_dict = {}
for vehicle, v_group in df.groupby("배차계획", sort=False):
    unique_addrs = v_group.sort_values("도로망거리_km")["배송지주소"].unique()
    addr_to_seq = {addr: f"{i+1}차 방문" for i, addr in enumerate(unique_addrs)}
    for idx, row in v_group.iterrows():
        seq_dict[idx] = addr_to_seq[row["배송지주소"]]

df["경유순서"] = df.index.map(seq_dict)

# --- 6. 대시보드 지표 카드 (KPI) ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("총 배송 건수", f"{len(df)} 건")
col2.metric("총 요청 수량", f"{df['요청수량'].sum()} 대")
col3.metric("총 필요 차량 수", f"{vehicle_counter - 1} 대")
col4.metric(
    "총 도로망 이동거리",
    f"{df['도로망거리_km'].sum():.1f} km" if kakao_api_key else "-",
)
col5.metric(
    "총 예상 이동시간",
    f"{df['이동시간_분'].sum()/60:.1f} 시간" if kakao_api_key else "-",
)

st.markdown("---")

# --- 7. 차량별 배차 요약 ---
st.subheader("📊 차량별 적재 및 이동 현황 요약")
summary_df = (
    df.groupby(["배차계획", "권역"])
    .agg(
        총적재수량=("요청수량", "sum"),
        경유지수=("배송지주소", "nunique"),
        평균이동거리_km=("도로망거리_km", "mean"),
        평균이동시간_분=("이동시간_분", "mean"),
    )
    .reset_index()
)

summary_df["평균이동거리_km"] = summary_df["평균이동거리_km"].round(1)
summary_df["평균이동시간_분"] = summary_df["평균이동시간_분"].round(1)

st.dataframe(
    summary_df[
        [
            "배차계획",
            "권역",
            "총적재수량",
            "경유지수",
            "평균이동거리_km",
            "평균이동시간_분",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

# --- 8. 상세 배송 리스트 ---
st.subheader("📋 차량별 상세 경유 배송 순서 및 도로망 경로 정보")

selected_region = st.multiselect(
    "권역 필터 선택",
    options=df["권역"].unique(),
    default=df["권역"].unique(),
)
filtered_df = df[df["권역"].isin(selected_region)].copy()

filtered_df = filtered_df.sort_values(
    by=["배차계획", "경유순서", "도로망거리_km"]
).reset_index(drop=True)

display_df = filtered_df.copy()
display_df["배차계획_표시"] = display_df["배차계획"].mask(
    display_df["배차계획"].duplicated(), ""
)

# 🔥 받는사람, 전화번호, 요청담당자명 컬럼 추가
cols_to_display = [
    "배차계획_표시",
    "경유순서",
    "권역",
    "거래처명",
    "배송지주소",
    "받는사람",
    "전화번호",
    "요청담당자명",
    "품목",
    "요청수량",
]

if kakao_api_key:
    cols_to_display.extend(["도로망거리_km", "이동시간_분"])

# hide_index=True로 인덱스열 제거하여 표기
st.dataframe(
    display_df[cols_to_display].rename(columns={"배차계획_표시": "배차계획"}),
    use_container_width=True,
    hide_index=True,
)
