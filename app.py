import io
import math
import re
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
    help="입력 시 카카오 도로망 거리/시간을 정밀 계산합니다. 미입력 시 직선거리 기반 최적 순서로 동작합니다.",
)

st.sidebar.header("📁 데이터 업로드")
uploaded_file = st.sidebar.file_uploader(
    "자료샘플.xlsx 파일을 업로드하세요", type=["xlsx"]
)

# --- 데이터 업로드 여부 체크 ---
if uploaded_file is None:
    st.info("👈 좌측 사이드바에서 [자료샘플.xlsx] 파일을 업로드해 주세요.")
    st.stop()  # 파일이 업로드되지 않으면 여기서 실행을 멈춤

# 엑셀 파일 로드
df = pd.read_excel(uploaded_file)

# --- 배송지 주소 정제 함수 (도로명 또는 지번 주소 건물번호/번지수까지만 추출) ---
def clean_address(addr):
    if not isinstance(addr, str) or not addr.strip():
        return ""
    clean = addr.split("/")[0].split("(")[0].replace(",", " ").strip()
    
    doro_match = re.search(r"^(.*?[가-힣A-Za-z0-9]+(?:로|길)\s+\d+(?:-\d+)?)", clean)
    if doro_match:
        return doro_match.group(1).strip()
        
    jibeon_match = re.search(r"^(.*?[가-힣A-Za-z0-9]+(?:읍|면|동|리)\s+\d+(?:-\d+)?)", clean)
    if jibeon_match:
        return jibeon_match.group(1).strip()
        
    return clean

# 배송지주소 정제 적용
df["배송지주소"] = df["배송지주소"].apply(clean_address)

for col in ["받는사람", "전화번호", "요청담당자명"]:
    if col not in df.columns:
        df[col] = "-"

START_ADDRESS = "경기도 용인시 당하로 159"

# --- 하버사인 공식 (직선거리 계산함수) ---
def calculate_haversine(lon1, lat1, lon2, lat2):
    R = 6371.0 # 지구 반지름(km)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- 2. 주소 좌표 변환 및 무료 지오코더 ---
@st.cache_data
def get_free_coordinates(address):
    clean_addr = clean_address(address)
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={clean_addr}"
    headers = {"User-Agent": "StreamlitKoreaDeliveryApp/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200 and len(res.json()) > 0:
            return float(res.json()[0]["lon"]), float(res.json()[0]["lat"])
    except Exception:
        pass
    return 127.17, 37.24

@st.cache_data
def get_coordinates(address, api_key):
    clean_addr = clean_address(address)
    if not api_key:
        return get_free_coordinates(clean_addr)
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": clean_addr}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            docs = res.json().get("documents")
            if docs:
                return float(docs[0]["x"]), float(docs[0]["y"])
    except Exception:
        pass
    return get_free_coordinates(clean_addr)

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
    elif "충남" in addr_str or "충청남도" in addr_str or "대전" in addr_str or "세종" in addr_str:
        return "충청권(충남/대전)"
    elif "전북" in addr_str or "전북특별자치도" in addr_str or "전라북도" in addr_str:
        return "호남권(전북)"
    elif "전남" in addr_str or "전라남도" in addr_str or "광주" in addr_str:
        return "호남권(전남/광주)"
    elif "경북" in addr_str or "경상북도" in addr_str or "대구" in addr_str:
        return "영남권(경북/대구)"
    elif "경남" in addr_str or "경상남도" in addr_str or "부산" in addr_str or "울산" in addr_str:
        return "영남권(경남/부산)"
    elif "강원" in addr_str:
        return "강원권"
    else:
        return "기타권역"

df["권역"] = df["배송지주소"].apply(get_region)

# --- 4. 좌표 계산 및 이동거리 산출 ---
coords_list = [get_coordinates(addr, kakao_api_key) for addr in df["배송지주소"]]
df["경도"] = [c[0] for c in coords_list]
df["위도"] = [c[1] for c in coords_list]

if kakao_api_key:
    route_results = [
        get_kakao_route_info((start_lng, start_lat), (row["경도"], row["위도"]), kakao_api_key)
        for _, row in df.iterrows()
    ]
    df["도로망거리_km"] = [r[0] for r in route_results]
    df["이동시간_분"] = [r[1] for r in route_results]
    st.sidebar.success("✅ 카카오 도로망 API 연동 완료")
else:
    df["도로망거리_km"] = [
        round(calculate_haversine(start_lng, start_lat, row["경도"], row["위도"]), 1)
        for _, row in df.iterrows()
    ]
    df["이동시간_분"] = round(df["도로망거리_km"] * 1.5, 1)
    st.sidebar.info("ℹ️ 직선거리 기반 모드로 동작 중 (카카오 API 입력 시 도로망 거리로 자동 전환)")

df = df.sort_values(by=["도로망거리_km", "배송지주소"]).reset_index(drop=True)

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
            v_list = [f"차량 {vehicle_counter + i:02d}" for i in range(trucks_needed)]
            vehicle_counter += trucks_needed
            v_str = f"[단독배차] {region} ({addr_qty}대 / 1톤 {','.join(v_list)})"
            for idx in addr_df.index:
                dispatch_dict[idx] = v_str
        else:
            if current_truck_num is None or (current_truck_qty + addr_qty > 70):
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
    sorted_unique_addrs = v_group.sort_values("도로망거리_km")["배송지주소"].unique()
    addr_to_seq = {addr: i + 1 for i, addr in enumerate(sorted_unique_addrs)}
    for idx, row in v_group.iterrows():
        seq_dict[idx] = addr_to_seq[row["배송지주소"]]

df["경유순서_숫자"] = df.index.map(seq_dict)
df["경유순서"] = df["경유순서_숫자"].apply(lambda x: f"{x}차 방문")

# --- 6. 대시보드 지표 카드 ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("총 배송 건수", f"{len(df)} 건")
col2.metric("총 요청 수량", f"{df['요청수량'].sum()} 대")
col3.metric("총 필요 차량 수", f"{vehicle_counter - 1} 대")
col4.metric("총 이동거리", f"{df['도로망거리_km'].sum():.1f} km")
col5.metric("총 예상 이동시간", f"{df['이동시간_분'].sum()/60:.1f} 시간")

st.markdown("---")

# --- 7. 대한민국 지도 기반 경유 순서 표현 (Folium) ---
st.subheader("🗺️ 대한민국 전용 지도 - 차량별 경유 순서(숫자 마커) 노선도")

map_vehicles = df["배차계획"].unique().tolist()
selected_vehicle_map = st.selectbox("노선도를 확인해볼 차량을 선택하세요", options=map_vehicles)

vehicle_map_df = (
    df[df["배차계획"] == selected_vehicle_map]
    .sort_values("경유순서_숫자")
    .drop_duplicates(subset=["배송지주소"])
    .copy()
)

center_lat = vehicle_map_df["위도"].iloc[0] if len(vehicle_map_df) > 0 else start_lat
center_lng = vehicle_map_df["경도"].iloc[0] if len(vehicle_map_df) > 0 else start_lng

m = folium.Map(
    location=[center_lat, center_lng],
    zoom_start=9,
    tiles="OpenStreetMap",
)

folium.Marker(
    location=[start_lat, start_lng],
    popup="<b>[출발지]</b> 용인 물류센터",
    tooltip="출발지: 용인시 당하로 159",
    icon=folium.Icon(color="red", icon="home", prefix="fa"),
).add_to(m)

path_coordinates = [(start_lat, start_lng)]

for _, row in vehicle_map_df.iterrows():
    lat, lng = row["위도"], row["경도"]
    seq_num = row["경유순서_숫자"]
    path_coordinates.append((lat, lng))

    same_addr_rows = df[(df["배차계획"] == selected_vehicle_map) & (df["배송지주소"] == row["배송지주소"])]
    total_qty = same_addr_rows["요청수량"].sum()
    names = ", ".join(same_addr_rows["거래처명"].unique())

    icon_html = f"""
    <div style="
        background-color: #007bff;
        border: 2px solid white;
        border-radius: 50%;
        color: white;
        font-weight: bold;
        text-align: center;
        width: 32px;
        height: 32px;
        line-height: 28px;
        font-size: 15px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.4);
    ">{seq_num}</div>
    """

    popup_text = f"""
    <div style="width: 220px;">
        <b style="color:#007bff;">[{seq_num}차 방문지]</b><br>
        <b>거래처:</b> {names}<br>
        <b>총 수량:</b> {total_qty} 대<br>
        <b>주소:</b> {row['배송지주소']}<br>
        <b>거리:</b> 출발지로부터 {row['도로망거리_km']} km
    </div>
    """

    folium.Marker(
        location=[lat, lng],
        popup=folium.Popup(popup_text, max_width=260),
        tooltip=f"{seq_num}차 방문: {names}",
        icon=DivIcon(
            icon_size=(32, 32), icon_anchor=(16, 16), html=icon_html
        ),
    ).add_to(m)

folium.PolyLine(
    locations=path_coordinates,
    color="#0056b3",
    weight=4,
    opacity=0.8,
    dash_array="6, 6",
).add_to(m)

st_folium(m, width="100%", height=520)

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
    "도로망거리_km",
    "이동시간_분",
]

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
            "도로망거리_km",
            "이동시간_분",
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
