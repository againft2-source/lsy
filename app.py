import io
import math
import folium
from folium.features import DivIcon
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

# 1. 페이지 설정
st.set_page_config(page_title="배송 경로 최적화 & 배차 대시보드", layout="wide")

st.title("🚚 배송 경로 최적화 & 배차 대시보드")
st.caption(
    "출발지: 경기도 용인시 당하로 159 | 차량 기준: 1톤(최대 70대 적재) | "
    "대한민국 지도 기반 경유 순서(1, 2, 3...) 마커 표현"
)

# --- 사이드바 설정 및 API Key 입력 ---
st.sidebar.header("🔑 API 설정")
kakao_api_key = st.sidebar.text_input(
    "Kakao REST API Key (선택)",
    type="password",
    help="입력 시 카카오 도로망 거리/시간을 정밀 계산합니다. 미입력 시 무료 지오코딩 및 기본 경유 순서로 동작합니다.",
)

st.sidebar.header("📁 데이터 업로드")
uploaded_file = st.sidebar.file_uploader(
    "자료샘플.xlsx 파일을 업로드하세요", type=["xlsx"]
)

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
else:
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

for col in ["받는사람", "전화번호", "요청담당자명"]:
    if col not in df.columns:
        df[col] = "-"

START_ADDRESS = "경기도 용인시 당하로 159"


# --- 2. 주소 좌표 변환 및 무료 지오코더 ---
@st.cache_data
def get_free_coordinates(address):
    clean_addr = address.split("/")[0].strip()
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={clean_addr}"
    headers = {"User-Agent": "StreamlitKoreaDeliveryApp/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200 and len(res.json()) > 0:
            return float(res.json()[0]["lon"]), float(res.json()[0]["lat"])
    except Exception:
        pass
    return 127.17, 37.24  # 용인 센터 기본 좌표


@st.cache_data
def get_coordinates(address, api_key):
    if not api_key:
        return get_free_coordinates(address)
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": address.split("/")[0].strip()}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            docs = res.json().get("documents")
            if docs:
                return float(docs[0]["x"]), float(docs[0]["y"])
    except Exception:
        pass
    return get_free_coordinates(address)


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


# --- 3. 권역 구분 ---
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

# --- 4. 좌표 계산 및 이동거리 산출 ---
coords_list = [
    get_coordinates(addr, kakao_api_key) for addr in df["배송지주소"]
]
df["경도"] = [c[0] for c in coords_list]
df["위도"] = [c[1] for c in coords_list]

if kakao_api_key:
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
    df["도로망거리_km"] = 0.0
    df["이동시간_분"] = 0.0
    st.sidebar.info("ℹ️ 오픈 지오코더 기본 모드로 동작 중")

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

seq_dict = {}
for vehicle, v_group in df.groupby("배차계획", sort=False):
    unique_addrs = v_group.sort_values("도로망거리_km")["배송지주소"].unique()
    addr_to_seq = {
        addr: i + 1 for i, addr in enumerate(unique_addrs)
    }  # 숫자 순서 저장
    for idx, row in v_group.iterrows():
        seq_dict[idx] = addr_to_seq[row["배송지주소"]]

df["경유순서_숫자"] = df.index.map(seq_dict)
df["경유순서"] = df["경유순서_숫자"].apply(lambda x: f"{x}차 방문")

# --- 6. 대시보드 지표 카드 ---
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

# --- 7. 대한민국 지도 기반 경유 순서 표현 (Folium) ---
st.subheader("🗺️ 대한민국 전용 지도 - 차량별 경유 순서(숫자 마커) 노선도")

map_vehicles = df["배차계획"].unique().tolist()
selected_vehicle_map = st.selectbox(
    "노선도를 확인해볼 차량을 선택하세요", options=map_vehicles
)

vehicle_map_df = (
    df[df["배차계획"] == selected_vehicle_map]
    .sort_values("경유순서_숫자")
    .copy()
)

# Folium 대한민국 중심 지도 객체 생성
m = folium.Map(
    location=[start_lat, start_lng],
    zoom_start=9,
    tiles="OpenStreetMap",  # 필요 시 Vworld 등 한국 전용 지도 타일 교체 가능
)

# 1) 출발지 마커 (빨간색)
folium.Marker(
    location=[start_lat, start_lng],
    popup="<b>[출발지]</b> 용인 물류센터",
    tooltip="출발지: 용인시 당하로 159",
    icon=folium.Icon(color="red", icon="home", prefix="fa"),
).add_to(m)

# 2) 경유지 마커 (경유 순서 번호 표시)
path_coordinates = [(start_lat, start_lng)]

for _, row in vehicle_map_df.iterrows():
    lat, lng = row["위도"], row["경도"]
    seq_num = row["경유순서_숫자"]
    path_coordinates.append((lat, lng))

    # 숫자가 선명하게 각인된 Custom HTML Marker 생성
    icon_html = f"""
    <div style="
        background-color: #007bff;
        border: 2px solid white;
        border-radius: 50%;
        color: white;
        font-weight: bold;
        text-align: center;
        width: 30px;
        height: 30px;
        line-height: 26px;
        font-size: 14px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.4);
    ">{seq_num}</div>
    """

    popup_text = f"""
    <div style="width: 200px;">
        <b>[{seq_num}차 방문] {row['거래처명']}</b><br>
        수량: {row['요청수량']} 대<br>
        주소: {row['배송지주소']}<br>
        수령인: {row['받는사람']} ({row['전화번호']})
    </div>
    """

    folium.Marker(
        location=[lat, lng],
        popup=folium.Popup(popup_text, max_width=250),
        tooltip=f"{seq_num}차 방문지: {row['거래처명']}",
        icon=DivIcon(
            icon_size=(30, 30), icon_anchor=(15, 15), html=icon_html
        ),
    ).add_to(m)

# 3) 차량 점선 이동 경로선 (PolyLine) Draw
folium.PolyLine(
    locations=path_coordinates,
    color="#0056b3",
    weight=3.5,
    opacity=0.8,
    dash_array="6, 6",
).add_to(m)

# Streamlit 내에 Folium 지도 렌더링
st_folium(m, width="100%", height=500)

st.markdown("---")

# --- 8. 상세 배송 리스트 ---
st.subheader("📋 차량별 상세 경유 배송 순서 및 도로망 경로 정보")

selected_region = st.multiselect(
    "권역 필터 선택",
    options=df["권역"].unique(),
    default=df["권역"].unique(),
)
filtered_df = df[df["권역"].isin(selected_region)].copy()
filtered_df = filtered_df.sort_values(
    by=["배차계획", "경유순서_숫자", "도로망거리_km"]
).reset_index(drop=True)

display_df = filtered_df.copy()
display_df["배차계획_표시"] = display_df["배차계획"].mask(
    display_df["배차계획"].duplicated(), ""
)

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

# 엑셀 다운로드 버퍼
output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    filtered_df[
        [
            "배차계획",
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
    ].to_excel(writer, index=False, sheet_name="상세배차계획")
processed_data = output.getvalue()

btn_col1, btn_col2 = st.columns([1, 4])
with btn_col1:
    st.download_button(
        label="📥 배차 결과 엑셀 다운로드",
        data=processed_data,
        file_name="배차최적화결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with btn_col2:
    if st.button("🖨️ 대시보드 인쇄 / PDF 저장"):
        st.components.v1.html("<script>window.print();</script>", height=0)

st.dataframe(
    display_df[cols_to_display].rename(columns={"배차계획_표시": "배차계획"}),
    use_container_width=True,
    hide_index=True,
)