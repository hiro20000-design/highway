import math
import urllib.parse
import re
import streamlit as st
import requests
import polyline

st.set_page_config(page_title="完全全国対応スマート高速ルーター", page_icon="🚗", layout="centered")

# ==========================================
# 🔧 訪問者カウンター (GAS連携)
# ==========================================
GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz1ngul4BEJ7Xpmx-LfVNrEwe_qcw79v6GYxr514mMh6g-rkmbhLOnmTSEFsNUuNqXQ/exec"

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
    出発地 = st.text_input("出発地", value="")
with col2:
    目的地 = st.text_input("目的地", value="")

経由地1 = st.text_input("経由地1（任意）", value="")

col3, col4 = st.columns(2)
with col3:
    高速予算上限円 = st.number_input("高速予算上限 (円)", value=3000, step=500)
with col4:
    最大所要時間_時間 = st.number_input("最大所要時間 (時間) ※0で無制限", value=0.0, step=0.5)

col5, col6 = st.columns(2)
with col5:
    ETC割引 = st.checkbox("ETC割引（深夜/休日30%引）を適用", value=True)
with col6:
    多段ワープ = st.checkbox("多段ワープ（1回余分に乗り降りして節約）を探索", value=True)

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
# 1. 座標取得
# ==========================================
@st.cache_data(ttl=86400)
def get_coords(place_name):
    if not place_name or not place_name.strip():
        return None, None
    
    base = place_name.strip()
    queries = [base]
    if not base.endswith(("町", "市", "区", "村", "駅", "IC", "JCT")):
        queries.append(base + "町")
        queries.append(base + "駅")
        
    match = re.search(r'(.+?[市区町村])', base)
    if match:
        queries.append(match.group(1))

    for q in queries:
        gsi_url = f"https://msearch.gsi.go.jp/msearch/msearch.jsp?keyword={urllib.parse.quote(q)}"
        try:
            res = requests.get(gsi_url, timeout=5).json()
            if res and len(res) > 0:
                coords = res[0]["geometry"]["coordinates"]
                return float(coords[1]), float(coords[0])
        except:
            pass

    headers = {"User-Agent": "SmartHighwayRouterJapan_PersonalApp/6.0"}
    for q in queries:
        nom_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(q + ', Japan')}&format=json&limit=1"
        try:
            res = requests.get(nom_url, headers=headers, timeout=5).json()
            if res and len(res) > 0:
                return float(res[0]["lat"]), float(res[0]["lon"])
        except:
            pass

    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

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

def calc_national_toll(ic_start, ic_end, hwy_km, discount=False):
    if hwy_km <= 1.0: return 0
    metro_ratio = 0.5 if (ic_start["is_metro"] or ic_end["is_metro"]) else 0.0
    if ic_start["is_metro"] and ic_end["is_metro"]: metro_ratio = 1.0
    base_rate = (24.6 * (1.0 - metro_ratio)) + (29.52 * metro_ratio)
    tc = 150.0
    if hwy_km <= 100: dist_cost = hwy_km * base_rate
    elif hwy_km <= 200: dist_cost = (100 * base_rate) + ((hwy_km - 100) * base_rate * 0.75)
    else: dist_cost = (100 * base_rate) + (100 * base_rate * 0.75) + ((hwy_km - 200) * base_rate * 0.70)
    fare = (tc + dist_cost) * 1.10
    if discount:
        discountable_portion = fare * (1.0 - metro_ratio)
        fare = (discountable_portion * 0.70) + (fare * metro_ratio)
    return int(round(fare, -1))

RAW_DATA_LINES = [
    # 北海道 (hokkaido)
    "函館,41.8112,140.7512,hokkaido", "大沼公園,41.9765,140.6625,hokkaido", "八雲,42.2412,140.2512,hokkaido", 
    "長万部,42.5112,140.3612,hokkaido", "伊達,42.4812,140.8612,hokkaido", "室蘭,42.3412,141.0012,hokkaido", 
    "登別東,42.4612,141.1612,hokkaido", "苫小牧西,42.6312,141.4812,hokkaido", "苫小牧東,42.6812,141.7312,hokkaido", 
    "千歳,42.8112,141.6212,hokkaido", "恵庭,42.8812,141.5612,hokkaido", "北広島,42.9612,141.5212,hokkaido", 
    "札幌南,43.0112,141.4612,hokkaido", "札幌,43.0712,141.4112,hokkaido", "小樽,43.1812,141.0112,hokkaido", 
    "江別東,43.0912,141.5812,hokkaido", "岩見沢,43.1812,141.7612,hokkaido", "美唄,43.3312,141.8612,hokkaido", 
    "滝川,43.5612,141.9312,hokkaido", "深川,43.7312,142.0412,hokkaido", "旭川鷹栖,43.8012,142.3412,hokkaido", 
    "旭川北,43.8312,142.4112,hokkaido", "士別剣淵,44.1412,142.3812,hokkaido", "夕張,42.9212,141.9612,hokkaido", 
    "占冠,42.9912,142.4012,hokkaido", "トマム,43.0612,142.6212,hokkaido", "十勝清水,43.0112,142.8812,hokkaido", 
    "音更帯広,42.9712,143.1812,hokkaido", "池田,42.9312,143.4612,hokkaido", "本別,43.1212,143.6012,hokkaido",
    "釧路,43.0112,144.3512,hokkaido", "北見,43.8012,143.8912,hokkaido",
    # 東北 (tohoku)
    "白河,37.1145,140.1652,tohoku", "矢吹,37.2012,140.3212,tohoku", "須賀川,37.2812,140.3512,tohoku",
    "郡山南,37.3612,140.3212,tohoku", "郡山,37.4251,140.3125,tohoku", "本宮,37.5112,140.3812,tohoku",
    "二本松,37.5812,140.4212,tohoku", "福島西,37.7412,140.4212,tohoku", "福島飯坂,37.8112,140.4612,tohoku",
    "国見,37.8812,140.5512,tohoku", "白石,38.0112,140.6312,tohoku", "村田,38.1112,140.7312,tohoku",
    "仙台南,38.2045,140.8212,tohoku", "仙台宮城,38.2612,140.8212,tohoku", "泉,38.3312,140.8812,tohoku",
    "大和,38.4412,140.8912,tohoku", "古川,38.5812,140.9312,tohoku", "築館,38.7312,141.0112,tohoku",
    "一関,38.9212,141.1112,tohoku", "平泉前沢,39.0212,141.1212,tohoku", "水沢,39.1412,141.1212,tohoku",
    "北上江釣子,39.2812,141.0912,tohoku", "花巻南,39.3612,141.1012,tohoku", "花巻,39.4112,141.1112,tohoku",
    "盛岡南,39.6582,141.1394,tohoku", "盛岡,39.7112,141.1012,tohoku", "滝沢,39.7712,141.1112,tohoku",
    "西根,39.9212,141.0912,tohoku", "安代,40.1112,141.0112,tohoku", "鹿角八幡平,40.1812,140.8112,tohoku",
    "十和田,40.2812,140.7612,tohoku", "小坂,40.3312,140.7312,tohoku", "碇ヶ関,40.4812,140.6312,tohoku",
    "大鰐弘前,40.5412,140.5412,tohoku", "黒石,40.6412,140.6112,tohoku", "浪岡,40.7112,140.6012,tohoku",
    "青森,40.7812,140.7241,tohoku", "山形蔵王,38.2412,140.3712,tohoku", "山形北,38.2912,140.3512,tohoku",
    "寒河江,38.3712,140.2612,tohoku", "鶴岡,38.7212,139.8112,tohoku", "酒田,38.8912,139.8612,tohoku",
    "横手,39.3112,140.5412,tohoku", "大曲,39.4412,140.4412,tohoku", "秋田南,39.6612,140.1512,tohoku",
    "秋田中央,39.7212,140.1612,tohoku", "能代南,40.1612,140.0312,tohoku", "いわき湯本,36.9912,140.8212,tohoku",
    "いわき中央,37.0612,140.8512,tohoku", "常磐富岡,37.3412,140.9812,tohoku", "南相馬,37.6312,140.9212,tohoku",
    "亘理,38.0312,140.8612,tohoku", "仙台港北,38.2812,140.9812,tohoku", "石巻河南,38.4412,141.2612,tohoku",
    "気仙沼中央,38.8912,141.5512,tohoku", "宮古中央,39.6312,141.9312,tohoku", "八戸,40.4812,141.4512,tohoku",
    "郡山東,37.4112,140.4312,tohoku", "磐梯熱海,37.4712,140.2612,tohoku", "猪苗代磐梯高原,37.5412,140.1112,tohoku",
    "会津若松,37.5212,139.9212,tohoku",
    # 関東・甲信越 (kanto)
    "三郷,35.8412,139.8612,kanto", "流山,35.8712,139.9112,kanto", "柏,35.8912,139.9512,kanto",
    "谷和原,35.9812,140.0212,kanto", "桜土浦,36.0612,140.1512,kanto", "土浦北,36.1112,140.1812,kanto",
    "千代田石岡,36.1712,140.2512,kanto", "岩間,36.2812,140.3012,kanto", "水戸,36.3712,140.3912,kanto",
    "那珂,36.4512,140.4612,kanto", "日立南太田,36.5212,140.5712,kanto", "日立中央,36.6012,140.6312,kanto",
    "北茨城,36.8012,140.7312,kanto",
    "水戸大洗,36.3312,140.5312,kanto", "水戸南,36.3385,140.4821,kanto", "茨城町東,36.3112,140.4412,kanto",
    "茨城町西,36.3112,140.3912,kanto", "友部,36.3312,140.3112,kanto", "笠間西,36.3612,140.2112,kanto",
    "桜川筑西,36.3512,140.1112,kanto", "真岡,36.4212,139.9812,kanto", "宇都宮上三川,36.4712,139.9012,kanto",
    "壬生,36.4512,139.8112,kanto", "都賀,36.4312,139.7412,kanto", "佐野田沼,36.3612,139.5812,kanto",
    "足利,36.3612,139.4612,kanto", "太田桐生,36.3412,139.3712,kanto", "太田薮塚,36.3512,139.3012,kanto",
    "伊勢崎,36.3412,139.2112,kanto", "駒形,36.3412,139.1412,kanto", "前橋南,36.3412,139.0912,kanto",
    "つくば牛久,36.0212,140.1212,kanto", "つくば中央,36.0582,140.0812,kanto", "常総,36.0412,139.9612,kanto",
    "坂東,36.0512,139.8812,kanto", "境古河,36.1112,139.8012,kanto", "五霞,36.1112,139.7312,kanto",
    "幸手,36.0812,139.7012,kanto", "白岡菖蒲,36.0465,139.6385,kanto", "桶川加納,36.0112,139.5812,kanto",
    "桶川北本,36.0112,139.5212,kanto", "川島,35.9812,139.4612,kanto", "坂戸,35.9612,139.4112,kanto",
    "圏央鶴ヶ島,35.9112,139.3612,kanto", "狭山日高,35.8612,139.3612,kanto", "入間,35.8112,139.3512,kanto",
    "青梅,35.8012,139.3012,kanto", "日の出,35.7412,139.2712,kanto", "あきる野,35.7112,139.2812,kanto",
    "八王子西,35.6712,139.2612,kanto", "高尾山,35.6212,139.2612,kanto", "相模原,35.5812,139.2812,kanto",
    "相模原愛川,35.5312,139.3412,kanto", "圏央厚木,35.4612,139.3612,kanto", "寒川北,35.3912,139.3812,kanto",
    "茅ヶ崎中央,35.3412,139.4012,kanto",
    "浦和,35.8912,139.7212,kanto", "岩槻,35.9329,139.7126,kanto", "蓮田,35.9912,139.6612,kanto",
    "久喜,36.0682,139.6468,kanto", "加須,36.1212,139.6212,kanto", "羽生,36.1612,139.5612,kanto",
    "館林,36.2312,139.5612,kanto", "佐野藤岡,36.3012,139.6112,kanto", "栃木,36.3912,139.6912,kanto",
    "鹿沼,36.5312,139.7812,kanto", "宇都宮,36.6342,139.8451,kanto", "上河内,36.7112,139.8812,kanto",
    "矢板,36.7912,139.9112,kanto", "西那須野塩原,36.9112,139.9512,kanto", "那須,37.0212,140.0612,kanto",
    "練馬,35.7512,139.6112,kanto", "所沢,35.8012,139.5212,kanto", "三芳,35.8312,139.5012,kanto",
    "川越,35.9012,139.4612,kanto", "鶴ヶ島,35.9312,139.3812,kanto", "東松山,36.0212,139.3912,kanto",
    "嵐山小川,36.0612,139.3112,kanto", "花園,36.1212,139.2212,kanto", "本庄児玉,36.2212,139.1712,kanto",
    "高崎,36.3212,139.0512,kanto", "前橋,36.3812,139.0412,kanto", "渋川伊香保,36.4812,139.0112,kanto",
    "沼田,36.6412,139.0612,kanto", "水上,36.7512,138.9712,kanto", "湯沢,36.9312,138.8112,kanto",
    "六日町,37.0612,138.8712,kanto", "小出,37.2312,138.9412,kanto", "越後川口,37.2712,138.8612,kanto",
    "長岡,37.4412,138.8041,hokuriku", "三条燕,37.6512,138.9112,hokuriku", "新潟西,37.8612,139.0041,hokuriku",
    "横浜町田,35.5112,139.4712,kanto", "海老名,35.4312,139.3812,kanto", "木更津金田,35.4212,139.9212,kanto",
    "市原,35.4912,140.1112,kanto", "成田,35.7812,140.3512,kanto",
    # 東海北陸道・北陸道・上信越道 (hokuriku)
    "一宮西,35.3054,136.7725,hokuriku", "岐阜各務原,35.3912,136.8512,hokuriku", "関,35.4812,136.9112,hokuriku", "美濃,35.5412,136.9212,hokuriku",
    "美並,35.6312,136.9512,hokuriku", "郡上八幡,35.7412,136.9612,hokuriku", "ぎふ大和,35.8012,136.9312,hokuriku", "白鳥,35.8812,136.8712,hokuriku",
    "高鷲,35.9712,136.8812,hokuriku", "ひるがの高原,36.0112,136.9012,hokuriku", "荘川,36.0512,136.9412,hokuriku", "飛騨清見,36.1612,137.0712,hokuriku",
    "白川郷,36.2612,136.9012,hokuriku", "五箇山,36.3812,136.9212,hokuriku", "福光,36.5412,136.9012,hokuriku", "小矢部砺波,36.6412,136.9612,hokuriku",
    "砺波,36.6512,136.9712,hokuriku", "小杉,36.7012,137.0812,hokuriku", "富山西,36.6812,137.1312,hokuriku", "富山,36.6712,137.1741,hokuriku",
    "富山東,36.6912,137.2412,hokuriku", "立山,36.6712,137.3312,hokuriku", "滑川,36.7412,137.3612,hokuriku", "魚津,36.8112,137.4212,hokuriku",
    "黒部,36.8712,137.4512,hokuriku", "朝日,36.9512,137.5512,hokuriku", "糸魚川,37.0312,137.8512,hokuriku", "上越,37.1812,138.2512,hokuriku",
    "柏崎,37.3512,138.5712,hokuriku", "金沢東,36.6012,136.6841,hokuriku", "金沢西,36.5712,136.6112,hokuriku", "小松,36.4112,136.4312,hokuriku",
    "加賀,36.2912,136.3012,hokuriku", "福井,36.0712,136.2541,hokuriku", "武生,35.9012,136.1912,hokuriku", "敦賀,35.6512,136.0841,hokuriku",
    "長野,36.5812,138.1812,hokuriku", "須坂長野東,36.6412,138.2612,hokuriku", "信州中野,36.7412,138.3312,hokuriku", "妙高高原,36.8712,138.2112,hokuriku",
    "上田菅平,36.4112,138.2812,hokuriku", "佐久,36.2712,138.4612,hokuriku", "碓氷軽井沢,36.2712,138.6412,hokuriku", "富岡,36.2412,138.8912,hokuriku",
    # 東名・東海環状・名神・伊勢湾岸道・名二環 (tomei)
    "一宮,35.2782,136.8485,tomei", "小牧,35.2934,136.9142,tomei", "春日井,35.2818,137.0142,tomei", "名古屋,35.1583,137.0137,tomei",
    "東名三好,35.1112,137.0812,tomei", "豊田,35.0504,137.1352,tomei", "豊田東,35.0381,137.1724,tomei",
    "豊田松平,35.0612,137.1812,tomei", "豊田勘八,35.1112,137.1912,tomei", "鞍ヶ池,35.0812,137.2112,tomei",
    "岡崎,34.9142,137.1856,tomei", "音羽蒲郡,34.8612,137.3012,tomei", "豊川,34.8312,137.4012,tomei",
    "浜松,34.7408,137.7709,tomei", "袋井,34.7612,137.9212,tomei", "掛川,34.7612,138.0112,tomei", "吉田,34.7812,138.2412,tomei",
    "静岡,34.9575,138.4060,tomei", "清水,35.0312,138.4812,tomei", "富士,35.1764,138.6475,tomei", "沼津,35.1312,138.8612,tomei",
    "御殿場,35.3022,138.9431,tomei", "大井松田,35.3312,139.1512,tomei", "秦野中井,35.3512,139.2212,tomei",
    "厚木,35.4218,139.3621,tomei", "東京,35.6263,139.6231,tomei",
    "名港中央,35.0505,136.8504,tomei", "大高,35.0614,136.9416,tomei", "名古屋南,35.0583,136.9248,tomei", 
    "飛島,35.0345,136.8123,tomei", "湾岸桑名,35.0358,136.6859,tomei", "東海,35.0369,136.9011,tomei",
    "清洲東,35.2158,136.8454,tomei", "楠,35.2285,136.9142,tomei", "名古屋西,35.1554,136.8142,tomei",
    # 新東名 (shin_tomei)
    "岡崎東,34.9312,137.2812,shin_tomei", "新城,34.9171,137.4801,shin_tomei",
    "浜松浜北,34.8212,137.7912,shin_tomei", "森掛川,34.8112,137.9512,shin_tomei", "島田金谷,34.8412,138.1212,shin_tomei",
    "新静岡,35.0315,138.3842,shin_tomei", "新清水,35.0712,138.4812,shin_tomei", "新富士,35.1952,138.6751,shin_tomei",
    "新御殿場,35.3188,138.9221,shin_tomei", "伊勢原大山,35.4212,139.2812,shin_tomei",
    # 中央道 (chuo)
    "多治見,35.3402,137.1147,chuo", "土岐,35.3612,137.1812,chuo", "瑞浪,35.3712,137.2512,chuo", "恵那,35.4412,137.4012,chuo",
    "中津川,35.4925,137.4727,chuo", "園原,35.4612,137.6512,chuo", "飯田山本,35.4812,137.7612,chuo", "飯田,35.4988,137.7946,chuo",
    "松川,35.6012,137.9012,chuo", "駒ヶ根,35.7312,137.9212,chuo", "伊那,35.8612,137.9412,chuo", "諏訪,35.9989,138.1136,chuo",
    "諏訪南,35.9212,138.2312,chuo", "小淵沢,35.8612,138.3112,chuo", "韮崎,35.7212,138.4312,chuo", "甲府昭和,35.6329,138.5442,chuo",
    "一宮御坂,35.6312,138.6812,chuo", "大月,35.6112,138.9312,chuo", "上野原,35.6212,139.1112,chuo", "相模湖,35.6112,139.1912,chuo",
    "八王子,35.6798,139.3364,chuo", "国立府中,35.6712,139.4412,chuo", "調布,35.6512,139.5512,chuo", "松本,36.2212,137.9312,chuo", "安曇野,36.3112,137.9112,chuo",
    # 関西・中国・四国・九州 (kansai_west)
    "大垣,35.3218,136.6214,kansai_west", "関ヶ原,35.3582,136.4612,kansai_west", "米原,35.3241,136.2914,kansai_west", "彦根,35.2612,136.2641,kansai_west",
    "八日市,35.0912,136.2212,kansai_west", "竜王,35.0512,136.1112,kansai_west", "栗東,35.0112,135.9912,kansai_west", "京都東,34.9912,135.8212,kansai_west",
    "京都南,34.9412,135.7541,kansai_west", "茨木,34.8312,135.5612,kansai_west", "吹田,34.7812,135.5391,kansai_west", "豊中,34.7612,135.4612,kansai_west",
    "西宮,34.7312,135.3512,kansai_west", "桑名,35.0612,136.6512,kansai_west", "四日市,34.9812,136.5812,kansai_west", "鈴鹿,34.9112,136.5012,kansai_west",
    "亀山,34.8612,136.4212,kansai_west", "甲賀土山,34.9412,136.2812,kansai_west", "信楽,34.9012,136.0512,kansai_west", "大津,34.9912,135.8612,kansai_west",
    "高槻,34.8612,135.6112,kansai_west", "神戸北,34.8412,135.1812,kansai_west", "神戸西,34.6982,135.0541,kansai_west", "三木小野,34.8112,134.9612,kansai_west",
    "加古川北,34.8412,134.8512,kansai_west", "姫路東,34.8312,134.7541,kansai_west", "姫路西,34.8412,134.6112,kansai_west", "龍野,34.8512,134.5312,kansai_west",
    "赤穂,34.7712,134.3812,kansai_west", "備前,34.7612,134.2312,kansai_west", "和気,34.8012,134.1412,kansai_west", "山陽,34.7412,134.0112,kansai_west",
    "岡山,34.6982,133.8841,kansai_west", "倉敷,34.6212,133.7612,kansai_west", "玉島,34.5712,133.6612,kansai_west", "笠岡,34.5312,133.5112,kansai_west",
    "福山東,34.5012,133.4112,kansai_west", "福山西,34.4712,133.2712,kansai_west", "尾道,34.4412,133.1812,kansai_west", "三原久井,34.4612,133.0512,kansai_west",
    "河内,34.4612,132.8912,kansai_west", "西条,34.4412,132.7312,kansai_west", "志和,34.4512,132.6312,kansai_west", "広島東,34.4312,132.5512,kansai_west",
    "広島,34.4512,132.5141,kansai_west", "五日市,34.4112,132.3612,kansai_west", "廿日市,34.3512,132.3112,kansai_west", "大竹,34.2212,132.2212,kansai_west",
    "岩国,34.1512,132.1612,kansai_west", "徳山東,34.0312,131.8612,kansai_west", "防府東,34.0612,131.6012,kansai_west", "山口,34.1312,131.4812,kansai_west",
    "小郡,34.1112,131.3912,kansai_west", "宇部,33.9912,131.2612,kansai_west", "下関,33.9812,130.9512,kansai_west", "米子,35.4212,133.3912,kansai_west",
    "松江中央,35.4512,133.0612,kansai_west", "出雲,35.3412,132.7212,kansai_west", "淡路,34.5812,135.0012,kansai_west", "洲本,34.3412,134.8612,kansai_west",
    "鳴門,34.1812,134.5912,kansai_west", "高松中央,34.3112,134.0741,kansai_west", "坂出,34.2912,133.8612,kansai_west", "善通寺,34.2312,133.7912,kansai_west",
    "川之江,33.9912,133.5812,kansai_west", "新居浜,33.9212,133.2912,kansai_west", "松山,33.8012,132.7912,kansai_west", "高知,33.5812,133.5712,kansai_west",
    "門司,33.9312,130.9512,kansai_west", "小倉東,33.8312,130.9112,kansai_west", "八幡,33.8212,130.7612,kansai_west", "若宮,33.7212,130.6312,kansai_west",
    "古賀,33.7212,130.4812,kansai_west", "福岡,33.6212,130.4541,kansai_west", "太宰府,33.5212,130.4912,kansai_west", "筑紫野,33.4712,130.5212,kansai_west",
    "鳥栖,33.3912,130.5212,kansai_west", "久留米,33.3212,130.5612,kansai_west", "八女,33.2212,130.5412,kansai_west", "南関,33.0612,130.5412,kansai_west",
    "植木,32.9112,130.7112,kansai_west", "熊本,32.7812,130.7741,kansai_west", "御船,32.7212,130.7912,kansai_west", "松橋,32.6412,130.7112,kansai_west",
    "八代,32.4912,130.6212,kansai_west", "人吉,32.2212,130.7512,kansai_west", "えびの,32.0412,130.8212,kansai_west", "宮崎,31.8812,131.3812,kansai_west",
    "溝辺鹿児島空港,31.8112,130.7212,kansai_west", "鹿児島,31.6012,130.5241,kansai_west", "佐賀大和,33.3212,130.2812,kansai_west", "武雄北方,33.2112,130.0512,kansai_west",
    "大村,32.9212,129.9612,kansai_west", "長崎,32.7412,129.8912,kansai_west", "日田,33.3312,130.9212,kansai_west", "湯布院,33.2512,131.3412,kansai_west", "大分,33.2112,131.5912,kansai_west",
    # 追加：関西・中国・四国・九州ハブIC
    "天理,34.6012,135.8312,kansai_west", "香芝,34.5512,135.6912,kansai_west", "和歌山,34.2412,135.1912,kansai_west",
    "海南,34.1512,135.2112,kansai_west", "御坊,33.9012,135.1612,kansai_west", "田辺,33.7412,135.3912,kansai_west",
    "津山,35.0612,134.0012,kansai_west", "新見,34.9812,133.4712,kansai_west", "三次,34.7912,132.8512,kansai_west",
    "徳島,34.0912,134.5412,kansai_west", "池田,34.0312,133.8112,kansai_west",
    "延岡,32.5512,131.6512,kansai_west", "日向,32.4112,131.6012,kansai_west"
]

all_ics = []
for entry in RAW_DATA_LINES:
    parts = [p.strip() for p in entry.split(",") if p.strip()]
    if len(parts) >= 4:
        name = parts[0] if parts[0].endswith("IC") else parts[0] + "IC"
        all_ics.append({"name": name, "lat": float(parts[1]), "lon": float(parts[2]), "group": parts[3]})

# ==========================================
# 2. 実行ロジック
# ==========================================
if st.button("🚀 最適ルートを計算する", type="primary"):
    if not 出発地.strip() or not 目的地.strip():
        st.error("❌ 出発地と目的地を入力してください。")
        st.stop()

    if GAS_WEBHOOK_URL and GAS_WEBHOOK_URL.startswith("https://"):
        try:
            route_info = urllib.parse.quote(f"{出発地} ➔ {目的地}")
            requests.get(f"{GAS_WEBHOOK_URL}?action=検索実行&route={route_info}", timeout=2)
        except:
            pass

    with st.spinner(f"🛰️ 【{選択された路線ラベル}】に沿って総当たり計算を開始します..."):
        limit_time_min = int(最大所要時間_時間 * 60)
        route_key = 路線オプション[選択された路線ラベル]
        
        s_lat, s_lon = get_coords(出発地.strip())
        e_lat, e_lon = get_coords(目的地.strip())
        if not s_lat:
            st.error(f"❌ 出発地「{出発地}」の座標が取得できませんでした。住所を少し省略してお試しください。")
            st.stop()
        if not e_lat:
            st.error(f"❌ 目的地「{目的地}」の座標が取得できませんでした。住所を少し省略してお試しください。")
            st.stop()

        direct_dist = haversine(s_lat, s_lon, e_lat, e_lon)

        anchor_name = None
        if route_key == "shin_tomei": anchor_name = "新静岡IC"
        elif route_key == "tomei": anchor_name = "静岡IC"
        elif route_key == "chuo": anchor_name = "諏訪IC"
        elif route_key == "hokuriku": anchor_name = "郡上八幡IC"
        elif route_key == "kansai": anchor_name = "彦根IC"

        route_points = [(s_lat, s_lon)]
        if 経由地1.strip():
            v_lat, v_lon = get_coords(経由地1.strip())
            if not v_lat:
                st.error(f"❌ 経由地「{経由地1}」の座標が取得できませんでした。")
                st.stop()
            route_points.append((v_lat, v_lon))
        
        if anchor_name:
            a_lat, a_lon = get_coords(anchor_name)
            if a_lat:
                detour_dist = haversine(s_lat, s_lon, a_lat, a_lon) + haversine(a_lat, a_lon, e_lat, e_lon)
                if detour_dist <= direct_dist * 1.6:
                    route_points.append((a_lat, a_lon))
                else:
                    st.info(f"ℹ️ 選択された優先ルート（{選択された路線ラベル}）は目的地と方向が異なるため、最短道なりルートで自動計算しました。")

        route_points.append((e_lat, e_lon))

        loc_str = ";".join([f"{c[1]},{c[0]}" for c in route_points])
        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{loc_str}?overview=full&geometries=polyline"
        try:
            osrm_res = requests.get(osrm_url, timeout=12).json()
            if osrm_res.get("code") != "Ok": raise Exception()
            route_geom = osrm_res["routes"][0]["geometry"]
            route_coords = polyline.decode(route_geom)
        except:
            st.error("❌ ルートデータの取得に失敗しました。時間をおいて再実行してください。")
            st.stop()

        cum_dists = [0.0]
        for i in range(1, len(route_coords)):
            cum_dists.append(cum_dists[-1] + haversine(route_coords[i-1][0], route_coords[i-1][1], route_coords[i][0], route_coords[i][1]))

        valid_ics = []
        for ic in all_ics:
            min_dist = float('inf')
            best_progress = 0
            for i, pt in enumerate(route_coords):
                d = haversine(ic["lat"], ic["lon"], pt[0], pt[1])
                if d < min_dist:
                    min_dist = d
                    best_progress = cum_dists[i]
            dist_from_start = haversine(s_lat, s_lon, ic["lat"], ic["lon"])
            dist_from_end = haversine(e_lat, e_lon, ic["lat"], ic["lon"])
            
            if min_dist <= 3.5 or dist_from_start <= 15.0 or dist_from_end <= 15.0:
                valid_ics.append({
                    "name": ic["name"], "lat": ic["lat"], "lon": ic["lon"],
                    "progress": best_progress,
                    "is_metro": 1 if check_metro(ic["lat"], ic["lon"]) else 0,
                    "group": ic["group"],
                    "access_start": dist_from_start * 1.25,
                    "access_end": dist_from_end * 1.25
                })

        valid_ics.sort(key=lambda x: x["progress"])
        filtered_ics = []
        for ic in valid_ics:
            if not filtered_ics or (ic["progress"] - filtered_ics[-1]["progress"]) > 1.5 or ic["access_start"] <= 15.0 or ic["access_end"] <= 15.0:
                filtered_ics.append(ic)

        candidates = []
        N = len(filtered_ics)

        for i in range(N):
            for j in range(i + 1, N):
                ic1, ic2 = filtered_ics[i], filtered_ics[j]
                if ic2["progress"] <= ic1["progress"]: continue

                hwy_km = max(ic2["progress"] - ic1["progress"], haversine(ic1["lat"], ic1["lon"], ic2["lat"], ic2["lon"]) * 1.15)
                if hwy_km < 10: continue
                
                local_km = ic1["access_start"] + ic2["access_end"]
                
                # 💡【重要修正】迂回率（Detour Ratio）の絶対制限フィルターを追加
                # 下道と高速を合わせた「実際の総移動距離」が、出発地～目的地の「直線距離」に対して極端に大きすぎる（大回りすぎる）場合は無効とする
                total_travel_dist = local_km + hwy_km
                if total_travel_dist > direct_dist * 1.7 + 15.0:
                    continue

                candidates.append({
                    "name": f"{出発地} ➔ {ic1['name']} ➔ {ic2['name']} ➔ {目的地}",
                    "detail": f"高速: 約{int(hwy_km)}km / 下道: 約{int(local_km)}km",
                    "time_min": calc_accurate_time(hwy_km, local_km, num_trips=1),
                    "toll": calc_national_toll(ic1, ic2, hwy_km, ETC割引),
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

                            h1 = max(ic2["progress"] - ic1["progress"], haversine(ic1["lat"], ic1["lon"], ic2["lat"], ic2["lon"]) * 1.15)
                            h2 = max(ic4["progress"] - ic3["progress"], haversine(ic3["lat"], ic3["lon"], ic4["lat"], ic4["lon"]) * 1.15)
                            warp_local = max((ic3["progress"] - ic2["progress"]), haversine(ic2["lat"], ic2["lon"], ic3["lat"], ic3["lon"]) * 1.15)
                            if h1 < 12 or h2 < 12 or warp_local < 8: continue

                            loc_tot = ic1["access_start"] + warp_local + ic4["access_end"]
                            hwy_tot = h1 + h2
                            
                            # 多段ワープ時も迂回率を厳格にチェック
                            total_travel_dist = loc_tot + hwy_tot
                            if total_travel_dist > direct_dist * 1.7 + 15.0:
                                continue

                            candidates.append({
                                "name": f"【多段】{出発地} ➔ {ic1['name']}~{ic2['name']} ➔ [下道] ➔ {ic3['name']}~{ic4['name']} ➔ {目的地}",
                                "detail": f"高速計: 約{int(hwy_tot)}km / 中継下道: 約{int(warp_local)}km / 総下道: 約{int(loc_tot)}km",
                                "time_min": calc_accurate_time(hwy_tot, loc_tot, num_trips=2),
                                "toll": calc_national_toll(ic1, ic2, h1, ETC割引) + calc_national_toll(ic3, ic4, h2, ETC割引),
                                "legs": [
                                    {"type": "local", "from": 出発地, "to": ic1['name']},
                                    {"type": "hwy", "from": ic1['name'], "to": ic2['name']},
                                    {"type": "local", "from": ic2['name'], "to": ic3['name']},
                                    {"type": "hwy", "from": ic3['name'], "to": ic4['name']},
                                    {"type": "local", "from": ic4['name'], "to": 目的地}
                                ]
                            })

        filtered = list(candidates)
        if limit_time_min > 0:
            filtered = [c for c in filtered if c["time_min"] <= limit_time_min]
        if 高速予算上限円 > 0:
            filtered = [c for c in filtered if c["toll"] <= 高速予算上限円]

        if not candidates:
            st.warning("⚠️ 指定された予算や時間の条件に収まるルートがありませんでした。予算を上げるか、時間を増やしてお試しください。")
        else:
            st.success(f"✨ 探索が完了しました！（道なりIC: {len(filtered_ics)}箇所）")
            
            selected = []
            true_fastest = min(candidates, key=lambda x: x["time_min"])
            f_copy = dict(true_fastest)
            f_copy["badge"] = "🚀 最速ルート（実走最短・参考）"
            selected.append(f_copy)

            if filtered:
                cheapest = min(filtered, key=lambda x: x["toll"])
                if cheapest["name"] != true_fastest["name"]:
                    c_copy = dict(cheapest)
                    c_copy["badge"] = "💰 条件内・最安コスパ"
                    selected.append(c_copy)

                fastest_in_cond = min(filtered, key=lambda x: x["time_min"])
                if fastest_in_cond["name"] != true_fastest["name"] and fastest_in_cond["name"] != cheapest["name"]:
                    fic_copy = dict(fastest_in_cond)
                    fic_copy["badge"] = "⚖️ 条件内・最速バランス"
                    selected.append(fic_copy)
            else:
                st.warning("⚠️ 指定された予算に収まるルートは見つかりませんでしたが、参考として上記の最速ルートを提示します。")

            for r in selected:
                h, m = divmod(r["time_min"], 60)
                time_str = f"{h}時間{m}分" if h > 0 else f"{m}分"

                with st.container():
                    st.markdown(f"### {r['badge']}")
                    st.markdown(f"**{r['name']}**")
                    st.write(f"{r['detail']} ／ ⏱️ **約 {time_str}** ／ 💴 **{r['toll']:,}円**")
                    
                    st.markdown("#### 区間別ナビ起動（タップ順に案内開始）:")
                    for idx, leg in enumerate(r["legs"]):
                        t_label = "【下道】" if leg["type"] == "local" else "【高速】"
                        avoid = "&avoid=tolls" if leg["type"] == "local" else ""
                        url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(leg['from'])}&destination={urllib.parse.quote(leg['to'])}&travelmode=driving{avoid}"
                        st.markdown(f"- 第{idx+1}区間 {t_label}: [{leg['from']} ➔ {leg['to']}]({url})")
                    st.markdown("---")
