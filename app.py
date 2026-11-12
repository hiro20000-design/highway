import math
import urllib.parse
from datetime import datetime, timedelta
import streamlit as st
import requests
import polyline

st.set_page_config(page_title="完全全国対応スマート高速ルーター", page_icon="🚗", layout="centered")

# ==========================================
# 🔧 訪問者カウンター (GAS連携)
# ==========================================
GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz1ngul4BEJ7Xpmx-LfVNrEwe_qcw79v6GYxr514mMh6g-rkmbhLOnmTSEFsNUuNqXQ/exec" # ←ここにGASのURLを貼り付けてください（空欄でも動きます）

if "counted" not in st.session_state:
    st.session_state.counted = True
    if GAS_WEBHOOK_URL and GAS_WEBHOOK_URL.startswith("https://"):
        try:
            requests.get(GAS_WEBHOOK_URL, timeout=2)
        except:
            pass

st.title("🚗 完全全国対応・多段ナビシミュレーター")

# ==========================================
# 📍 条件設定フォーム
# ==========================================
col1, col2 = st.columns(2)
with col1:
    出発地 = st.text_input("出発地", value="尾張一宮駅")
with col2:
    目的地 = st.text_input("目的地", value="富山駅")

経由地1 = st.text_input("経由地1（任意）", value="")

col3, col4 = st.columns(2)
with col3:
    高速予算上限円 = st.number_input("高速予算上限 (円)", value=3000, step=500)
with col4:
    ETC割引 = st.checkbox("ETC割引（深夜/休日30%引）を適用", value=True)

多段ワープ = st.checkbox("多段ワープ（1回余分に乗り降りして節約）を探索する", value=True)

# 優先路線の選択
路線オプション = {
    "🌐 お任せ (最短道なり)": "auto",
    "🚗 新東名経由 (120km/h快走)": "shin_tomei",
    "🚙 東名経由 (海岸線沿い)": "tomei",
    "⛰️ 中央道経由 (山梨・長野回り)": "chuo",
    "🏔️ 東海北陸道・北陸道経由": "hokuriku",
    "🚙 名神・新名神経由": "kansai"
}
選択された路線ラベル = st.selectbox("検索したい「優先ルート」を選択", list(路線オプション.keys()))

# ==========================================
# 1. 関数群
# ==========================================
@st.cache_data(ttl=3600)
def get_coords(place_name):
    if not place_name or not place_name.strip(): return None, None
    gsi_url = f"https://msearch.gsi.go.jp/msearch/msearch.jsp?keyword={urllib.parse.quote(place_name.strip())}"
    try:
        res = requests.get(gsi_url, timeout=5).json()
        if res: return res[0]["geometry"]["coordinates"][1], res[0]["geometry"]["coordinates"][0]
    except: pass
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371; dLat = math.radians(lat2 - lat1); dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def calc_accurate_time(hwy_km, local_km, num_trips=1):
    t_local = (local_km / 34.0) * 60
    t_hwy = (hwy_km / 88.0) * 60
    t_loss = num_trips * 4.0
    return int(t_local + t_hwy + t_loss)

def check_metro(lat, lon):
    if 35.35 <= lat <= 36.15 and 139.20 <= lon <= 140.10: return True
    if 35.00 <= lat <= 35.38 and 136.75 <= lon <= 137.25: return True
    if 34.55 <= lat <= 34.95 and 135.25 <= lon <= 135.85: return True
    return False

RAW_DATA_LINES = [
    "一宮西,35.3054,136.7725,hokuriku", "岐阜各務原,35.3912,136.8512,hokuriku", "関,35.4812,136.9112,hokuriku", "美濃,35.5412,136.9212,hokuriku",
    "美並,35.6312,136.9512,hokuriku", "郡上八幡,35.7412,136.9612,hokuriku", "ぎふ大和,35.8012,136.9312,hokuriku", "白鳥,35.8812,136.8712,hokuriku",
    "高鷲,35.9712,136.8812,hokuriku", "ひるがの高原,36.0112,136.9012,hokuriku", "荘川,36.0512,136.9412,hokuriku", "飛騨清見,36.1612,137.0712,hokuriku",
    "白川郷,36.2612,136.9012,hokuriku", "五箇山,36.3812,136.9212,hokuriku", "福光,36.5412,136.9012,hokuriku", "小矢部砺波,36.6412,136.9612,hokuriku",
    "砺波,36.6512,136.9712,hokuriku", "小杉,36.7012,137.0812,hokuriku", "富山西,36.6812,137.1312,hokuriku", "富山,36.6712,137.1741,hokuriku",
    "富山東,36.6912,137.2412,hokuriku", "立山,36.6712,137.3312,hokuriku", "滑川,36.7412,137.3612,hokuriku", "魚津,36.8112,137.4212,hokuriku",
    "黒部,36.8712,137.4512,hokuriku", "朝日,36.9512,137.5512,hokuriku", "糸魚川,37.0312,137.8512,hokuriku", "上越,37.1812,138.2512,hokuriku",
    "金沢東,36.6012,136.6841,hokuriku", "福井,36.0712,136.2541,hokuriku", "敦賀,35.6512,136.0841,hokuriku", "長岡,37.4412,138.8041,hokuriku", "新潟西,37.8612,139.0041,hokuriku",
    "一宮,35.2782,136.8485,tomei", "小牧,35.2934,136.9142,tomei", "春日井,35.2818,137.0142,tomei", "名古屋,35.1583,137.0137,tomei",
    "豊田,35.0504,137.1352,tomei", "岡崎,34.9142,137.1856,tomei", "浜松,34.7408,137.7709,tomei", "静岡,34.9575,138.4060,tomei",
    "富士,35.1764,138.6475,tomei", "御殿場,35.3022,138.9431,tomei", "厚木,35.4218,139.3621,tomei", "東京,35.6263,139.6231,tomei",
    "豊田東,35.0381,137.1724,shin_tomei", "新城,34.9171,137.4801,shin_tomei", "新静岡,35.0315,138.3842,shin_tomei", "新富士,35.1952,138.6751,shin_tomei", "新御殿場,35.3188,138.9221,shin_tomei",
    "多治見,35.3402,137.1147,chuo", "中津川,35.4925,137.4727,chuo", "飯田,35.4988,137.7946,chuo", "諏訪,35.9989,138.1136,chuo",
    "甲府昭和,35.6329,138.5442,chuo", "八王子,35.6798,139.3364,chuo",
    "白岡菖蒲,36.0465,139.6385,kanto", "久喜,36.0682,139.6468,kanto", "岩槻,35.9329,139.7126,kanto", "宇都宮,36.6342,139.8451,kanto",
    "白河,37.1145,140.1652,kanto", "郡山,37.4251,140.3125,kanto", "仙台南,38.2045,140.8212,kanto", "盛岡南,39.6582,141.1394,kanto", "青森,40.7812,140.7241,kanto",
    "大垣,35.3218,136.6214,kansai_west", "関ヶ原,35.3582,136.4612,kansai_west", "米原,35.3241,136.2914,kansai_west", "彦根,35.2612,136.2641,kansai_west",
    "京都南,34.9412,135.7541,kansai_west", "吹田,34.7812,135.5391,kansai_west", "四日市,34.9812,136.5812,kansai_west", "甲賀土山,34.9412,136.2812,kansai_west",
    "神戸西,34.6982,135.0541,kansai_west", "姫路東,34.8312,134.7541,kansai_west", "岡山,34.6982,133.8841,kansai_west", "広島,34.4512,132.5141,kansai_west",
    "福岡,33.6212,130.4541,kansai_west", "熊本,32.7812,130.7741,kansai_west", "鹿児島,31.6012,130.5241,kansai_west"
]

all_ics = []
for entry in RAW_DATA_LINES:
    parts = [p.strip() for p in entry.split(",") if p.strip()]
    if len(parts) >= 4:
        name = parts[0] if parts[0].endswith("IC") else parts[0] + "IC"
        all_ics.append({"name": name, "lat": float(parts[1]), "lon": float(parts[2]), "group": parts[3]})

def calc_national_toll(ic_start, ic_end, discount=False):
    km = abs(ic_end["progress"] - ic_start["progress"])
    if km <= 1.0: return 0
    metro_ratio = 0.5 if (ic_start["is_metro"] or ic_end["is_metro"]) else 0.0
    if ic_start["is_metro"] and ic_end["is_metro"]: metro_ratio = 1.0
    base_rate = (24.6 * (1.0 - metro_ratio)) + (29.52 * metro_ratio)
    tc = 150.0
    if km <= 100: dist_cost = km * base_rate
    elif km <= 200: dist_cost = (100 * base_rate) + ((km - 100) * base_rate * 0.75)
    else: dist_cost = (100 * base_rate) + (100 * base_rate * 0.75) + ((km - 200) * base_rate * 0.70)
    fare = (tc + dist_cost) * 1.10
    if discount:
        discountable_portion = fare * (1.0 - metro_ratio)
        fare = (discountable_portion * 0.70) + (fare * metro_ratio)
    return int(round(fare, -1))

# ==========================================
# 2. 実行ロジック
# ==========================================
if st.button("🚀 最適ルートを計算する", type="primary"):
    if not 出発地.strip() or not 目的地.strip():
        st.error("❌ 出発地と目的地を入力してください。")
        st.stop()

    with st.spinner(f"🛰️ 【{選択された路線ラベル}】に沿って総当たり計算を開始します..."):
        route_key = 路線オプション[選択された路線ラベル]
        
        anchor_name = None
        target_groups = []

        if route_key == "shin_tomei":
            anchor_name = "新静岡IC"
            target_groups = ["shin_tomei", "tomei", "kanto"]
        elif route_key == "tomei":
            anchor_name = "静岡IC"
            target_groups = ["tomei", "kanto"]
        elif route_key == "chuo":
            anchor_name = "諏訪IC"
            target_groups = ["chuo", "kanto"]
        elif route_key == "hokuriku":
            anchor_name = "郡上八幡IC"
            target_groups = ["hokuriku"]
        elif route_key == "kansai":
            anchor_name = "彦根IC"
            target_groups = ["kansai_west"]
        else:
            target_groups = ["hokuriku", "tomei", "shin_tomei", "chuo", "kanto", "kansai_west"]

        route_points = [出発地.strip()]
        if 経由地1.strip(): route_points.append(経由地1.strip())
        
        if anchor_name and anchor_name not in route_points and anchor_name != 目的地.strip():
            alat, _ = get_coords(anchor_name)
            if alat: route_points.append(anchor_name)
            
        if 目的地.strip() not in route_points:
            route_points.append(目的地.strip())

        r_coords = []
        for rp in route_points:
            lat, lon = get_coords(rp)
            if not lat:
                st.error(f"❌ 地点「{rp}」の座標が取得できませんでした。")
                st.stop()
            r_coords.append((lat, lon))

        loc_str = ";".join([f"{c[1]},{c[0]}" for c in r_coords])
        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{loc_str}?overview=full&geometries=polyline"
        try:
            osrm_res = requests.get(osrm_url, timeout=12).json()
            if osrm_res.get("code") != "Ok": raise Exception()
            route_geom = osrm_res["routes"][0]["geometry"]
            total_km = osrm_res["routes"][0]["distance"] / 1000
            route_coords = polyline.decode(route_geom)
        except:
            st.error("❌ ルートデータの取得に失敗しました。時間をおいて再実行してください。")
            st.stop()

        cum_dists = [0.0]
        for i in range(1, len(route_coords)):
            cum_dists.append(cum_dists[-1] + haversine(route_coords[i-1][0], route_coords[i-1][1], route_coords[i][0], route_coords[i][1]))

        valid_ics = []
        for ic in all_ics:
            if ic["group"] not in target_groups: continue
            min_dist = float('inf')
            best_progress = 0
            for i, pt in enumerate(route_coords):
                d = haversine(ic["lat"], ic["lon"], pt[0], pt[1])
                if d < min_dist:
                    min_dist = d
                    best_progress = cum_dists[i]
            if min_dist <= 2.5:
                valid_ics.append({
                    "name": ic["name"], "lat": ic["lat"], "lon": ic["lon"],
                    "progress": best_progress,
                    "is_metro": 1 if check_metro(ic["lat"], ic["lon"]) else 0,
                    "group": ic["group"]
                })

        valid_ics.sort(key=lambda x: x["progress"])
        filtered_ics = []
        for ic in valid_ics:
            if not filtered_ics or (ic["progress"] - filtered_ics[-1]["progress"]) > 3.0:
                filtered_ics.append(ic)

        candidates = []
        N = len(filtered_ics)

        for i in range(N):
            for j in range(i + 1, N):
                ic1, ic2 = filtered_ics[i], filtered_ics[j]
                if ic2["progress"] <= ic1["progress"]: continue
                if (ic1["group"] == "tomei" and ic2["group"] == "shin_tomei") or (ic1["group"] == "shin_tomei" and ic2["group"] == "tomei"):
                    continue

                hwy_km = ic2["progress"] - ic1["progress"]
                if hwy_km < 12: continue
                local_km = max(0, total_km - hwy_km)
                toll = calc_national_toll(ic1, ic2, ETC割引)

                if toll <= 高速予算上限円:
                    candidates.append({
                        "name": f"{出発地} ➔ {ic1['name']} ➔ {ic2['name']} ➔ {目的地}",
                        "detail": f"高速: 約{int(hwy_km)}km / 下道: 約{int(local_km)}km",
                        "time_min": calc_accurate_time(hwy_km, local_km, num_trips=1),
                        "toll": toll,
                        "legs": [
                            {"type": "local", "from": 出発地, "to": ic1['name']},
                            {"type": "hwy", "from": ic1['name'], "to": ic2['name']},
                            {"type": "local", "from": ic2['name'], "to": 目的地}
                        ]
                    })

        if 多段ワープ and N >= 4:
            step = 2 if N > 25 else 1
            for i in range(0, N - 3, step):
                for j in range(i + 1, N - 2, step):
                    for k in range(j + 1, N - 1, step):
                        for l in range(k + 1, N, step):
                            ic1, ic2, ic3, ic4 = filtered_ics[i], filtered_ics[j], filtered_ics[k], filtered_ics[l]
                            groups = {ic1["group"], ic2["group"], ic3["group"], ic4["group"]} - {"kanto"}
                            if "tomei" in groups and "shin_tomei" in groups: continue

                            h1 = ic2["progress"] - ic1["progress"]
                            h2 = ic4["progress"] - ic3["progress"]
                            warp_local = ic3["progress"] - ic2["progress"]
                            if h1 < 15 or h2 < 15 or warp_local < 10: continue

                            hwy_tot = h1 + h2
                            loc_tot = max(0, total_km - hwy_tot)
                            toll_tot = calc_national_toll(ic1, ic2, ETC割引) + calc_national_toll(ic3, ic4, ETC割引)

                            if toll_tot <= 高速予算上限円:
                                candidates.append({
                                    "name": f"【多段】{出発地} ➔ {ic1['name']}~{ic2['name']} ➔ [下道] ➔ {ic3['name']}~{ic4['name']} ➔ {目的地}",
                                    "detail": f"高速計: 約{int(hwy_tot)}km / 中継下道: 約{int(warp_local)}km / 総下道: 約{int(loc_tot)}km",
                                    "time_min": calc_accurate_time(hwy_tot, loc_tot, num_trips=2),
                                    "toll": toll_tot,
                                    "legs": [
                                        {"type": "local", "from": 出発地, "to": ic1['name']},
                                        {"type": "hwy", "from": ic1['name'], "to": ic2['name']},
                                        {"type": "local", "from": ic2['name'], "to": ic3['name']},
                                        {"type": "hwy", "from": ic3['name'], "to": ic4['name']},
                                        {"type": "local", "from": ic4['name'], "to": 目的地}
                                    ]
                                })

        if candidates:
            best = min(candidates, key=lambda x: x["toll"])
            st.success(f"✨ 予算内で最も安いルートが見つかりました！（道なりIC: {len(filtered_ics)}箇所）")
            
            h, m = divmod(best["time_min"], 60)
            time_str = f"{h}時間{m}分" if h > 0 else f"{m}分"

            st.markdown(f"### 💰 最安コスパ: {best['name']}")
            st.write(f"**詳細**: {best['detail']} ／ ⏱️ **約 {time_str}** ／ 💴 **{best['toll']:,}円**")
            
            st.markdown("#### 🗺️ 区間別ナビ起動（タップ順に案内開始）:")
            for idx, leg in enumerate(best["legs"]):
                t_label = "【下道】" if leg["type"] == "local" else "【高速】"
                avoid = "&avoid=tolls" if leg["type"] == "local" else ""
                url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(leg['from'])}&destination={urllib.parse.quote(leg['to'])}&travelmode=driving{avoid}"
                st.markdown(f"- 第{idx+1}区間 {t_label}: [{leg['from']} ➔ {leg['to']}]({url})")
        else:
            st.warning("⚠️ 指定された予算内に収まるルートが見つかりませんでした。予算を上げるか条件を変更してください。")
