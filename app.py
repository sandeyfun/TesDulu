import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import folium
import io
import base64
from streamlit_folium import st_folium

# --- 1. SETUP HALAMAN & SESSION STATE ---
st.set_page_config(page_title="Dashboard Kualitas Air", layout="wide")

# Session state untuk navigasi halaman dan carousel peta
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'
if 'selected_village' not in st.session_state:
    st.session_state['selected_village'] = None
if 'map_index' not in st.session_state:
    st.session_state['map_index'] = 0


# Fungsi navigasi
def pindah_halaman(halaman):
    st.session_state['page'] = halaman
    st.session_state['map_index'] = 0  # Reset peta ke index 0 (WQI) tiap buka daerah baru


# --- 2. FUNGSI MEMBACA & MEMPROSES DATA ---
@st.cache_data  # Cache agar tidak perlu load ulang data tiap interaksi
def load_data():
    df = pd.read_csv('telanganawaterdata.csv')
    # Mengganti koma jadi titik sesuai aturan pemrosesan data
    df = df.replace(',', '.', regex=True)
    df.columns = df.columns.str.strip()

    # Konversi kolom ke numerik
    params = ['longitude', 'latitude', 'TDS', 'EC', 'pH', 'F', 'NO3']
    for p in params:
        df[p] = pd.to_numeric(df[p], errors='coerce')

    df = df.dropna(subset=['Kode', 'village'] + params).copy()

    # Hitung WQI
    standar_wqi = {'pH': [8.5, 4], 'TDS': [1000, 4], 'EC': [1500, 3], 'F': [1.5, 5], 'NO3': [45, 5]}
    total_wi = sum([v[1] for v in standar_wqi.values()])
    df['WQI'] = 0
    for p, (si, wi) in standar_wqi.items():
        if p == 'pH':
            qi = ((df[p] - 7) / (si - 7)) * 100
            qi = qi.abs()
        else:
            qi = (df[p] / si) * 100
        df['WQI'] += (wi * qi)
    df['WQI'] = df['WQI'] / total_wi

    return df


df = load_data()


# --- 3. FUNGSI PEMBUAT PETA ---
def buat_peta_spesifik(df, param, titik_fokus):
    x, y = df['longitude'].values, df['latitude'].values
    grid_x, grid_y = np.mgrid[min(x):max(x):300j, min(y):max(y):300j]

    val = df[param].values
    grid_z = griddata((x, y), val, (grid_x, grid_y), method='linear')

    fig, ax = plt.subplots(figsize=(10, 10))
    fig.subplots_adjust(0, 0, 1, 1)
    ax.axis('off')

    # Atur level dan warna berdasarkan parameter
    if param == 'WQI':
        max_val = max(350, np.nanmax(val) + 50)
        levels = [0, 50, 100, 200, 300, max_val]
        colors = ['#00BFFF', '#32CD32', '#FFD700', '#FF8C00', '#FF0000']
        legenda_html = '''
        <div style="position: fixed; bottom: 30px; left: 30px; width: 200px; background-color: white; 
             border: 2px solid grey; z-index: 9999; font-size: 12px; padding: 10px; border-radius: 5px;">
             <b>Legenda WQI</b><br>
             <i style="background: #00BFFF; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> < 50: Sangat Baik<br>
             <i style="background: #32CD32; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> 50-100: Baik<br>
             <i style="background: #FFD700; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> 100-200: Buruk<br>
             <i style="background: #FF8C00; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> 200-300: Sngt Buruk<br>
             <i style="background: #FF0000; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> > 300: Tidak Layak
        </div>'''
    else:
        batas = {'TDS': 1000, 'EC': 1500, 'pH': 8.5, 'F': 1.5, 'NO3': 45}
        b = batas[param]
        levels = [0, b, np.nanmax(val) + b]
        colors = ['green', 'orange']
        legenda_html = f'''
        <div style="position: fixed; bottom: 30px; left: 30px; width: 200px; background-color: white; 
             border: 2px solid grey; z-index: 9999; font-size: 12px; padding: 10px; border-radius: 5px;">
             <b>Legenda {param}</b><br>
             <i style="background: green; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> Aman (&le; {b})<br>
             <i style="background: orange; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> Bahaya (> {b})
        </div>'''

    ax.contourf(grid_x, grid_y, grid_z, levels=levels, colors=colors, extend='max', alpha=0.5)

    img_data = io.BytesIO()
    plt.savefig(img_data, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    image_url = 'data:image/png;base64,' + base64.b64encode(img_data.getvalue()).decode('utf-8')

    # Inisialisasi Peta Folium
    m = folium.Map(location=[titik_fokus['latitude'], titik_fokus['longitude']], zoom_start=12, tiles='OpenStreetMap')
    bounds = [[min(y), min(x)], [max(y), max(x)]]

    folium.raster_layers.ImageOverlay(
        image=image_url, bounds=bounds, opacity=0.6, name=f'Zonasi {param}'
    ).add_to(m)

    # Tambahkan titik semua desa
    for i in range(len(x)):
        folium.CircleMarker(
            location=[y[i], x[i]], radius=2, color='black', fill=True
        ).add_to(m)

    # HIGHLIGHT desa yang dicari (Marker Merah Besar + Ikon Info)
    folium.Marker(
        location=[titik_fokus['latitude'], titik_fokus['longitude']],
        popup=f"<b>{titik_fokus['village']}</b><br>{param}: {titik_fokus[param]:.2f}",
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

    m.get_root().html.add_child(folium.Element(legenda_html))
    return m


# --- 4. HALAMAN UTAMA (HOME) ---
if st.session_state['page'] == 'home':
    st.title("💧 Sistem Pemetaan Kualitas Air")
    st.write("Silakan cari nama daerah atau lihat keseluruhan data.")

    # Tombol ke Data Sheets
    if st.button("📄 Lihat Data Sheets"):
        pindah_halaman('sheets')
        st.rerun()

    st.markdown("---")

    # Search Bar (Autocomplete dengan st.selectbox)
    # Tambahkan string kosong agar opsi pertama kosong (tidak auto-pilih)
    daftar_daerah = [""] + list(df['village'].unique())
    pilihan = st.selectbox("Cari nama daerah (Ketik untuk memunculkan suggestions):", daftar_daerah)

    if pilihan != "":
        st.session_state['selected_village'] = pilihan
        pindah_halaman('detail')
        st.rerun()

# --- 5. HALAMAN DATA SHEETS ---
elif st.session_state['page'] == 'sheets':
    st.title("📄 Data Sheets Kualitas Air")
    if st.button("⬅️ Kembali ke Home"):
        pindah_halaman('home')
        st.rerun()

    st.dataframe(df)

# --- 6. HALAMAN DETAIL DAERAH & PETA ---
elif st.session_state['page'] == 'detail':
    if st.button("⬅️ Kembali ke Home"):
        pindah_halaman('home')
        st.rerun()

    daerah = st.session_state['selected_village']
    data_daerah = df[df['village'] == daerah].iloc[0]

    st.title(f"📍 Kualitas Air: {daerah}")

    # Logika Penjelasan Status
    st.subheader("📊 Analisis Parameter")

    # WQI
    w = data_daerah['WQI']
    if w < 50:
        status_wqi = "Sangat Baik"
    elif w <= 100:
        status_wqi = "Baik"
    elif w <= 200:
        status_wqi = "Buruk"
    elif w <= 300:
        status_wqi = "Sangat Buruk"
    else:
        status_wqi = "Tidak Layak Konsumsi"
    st.markdown(f"**• WQI (Water Quality Index): {w:.2f}** ➔ Kategori: **{status_wqi}**")

    # TDS
    t = data_daerah['TDS']
    if t <= 1000:
        st.markdown(f"**• TDS: {t} mg/L** ➔ <span style='color:green'>Aman.</span>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"**• TDS: {t} mg/L** ➔ <span style='color:red'>Bahaya, karena melebihi batas aman 1000 mg/L (menandakan tingginya zat padat terlarut).</span>",
            unsafe_allow_html=True)

    # EC
    e = data_daerah['EC']
    if e <= 1500:
        st.markdown(f"**• EC: {e} µS/cm** ➔ <span style='color:green'>Aman.</span>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"**• EC: {e} µS/cm** ➔ <span style='color:red'>Bahaya, karena melebihi batas aman 1500 µS/cm (menandakan tingginya konduktivitas elektrik/mineral).</span>",
            unsafe_allow_html=True)

    # pH
    p = data_daerah['pH']
    if p <= 8.5:
        st.markdown(f"**• pH: {p}** ➔ <span style='color:green'>Aman.</span>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"**• pH: {p}** ➔ <span style='color:red'>Bahaya, karena melebihi batas 8.5 (air bersifat terlalu basa/alkali).</span>",
            unsafe_allow_html=True)

    # F
    f = data_daerah['F']
    if f <= 1.5:
        st.markdown(f"**• Fluoride (F): {f} mg/L** ➔ <span style='color:green'>Aman.</span>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"**• Fluoride (F): {f} mg/L** ➔ <span style='color:red'>Bahaya, karena melebihi batas 1.5 mg/L (bisa merusak gigi dan tulang).</span>",
            unsafe_allow_html=True)

    # NO3
    n = data_daerah['NO3']
    if n <= 45:
        st.markdown(f"**• Nitrat (NO3): {n} mg/L** ➔ <span style='color:green'>Aman.</span>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"**• Nitrat (NO3): {n} mg/L** ➔ <span style='color:red'>Bahaya, karena melebihi batas 45 mg/L (beracun, terutama untuk bayi).</span>",
            unsafe_allow_html=True)

    st.markdown("---")

    # Carousel Peta
    urutan_peta = ['WQI', 'TDS', 'EC', 'pH', 'F', 'NO3']
    idx = st.session_state['map_index']
    param_aktif = urutan_peta[idx]

    st.subheader(f"🗺️ Visualisasi Peta: {param_aktif}")

    # Navigasi Panah Kiri Kanan dengan Columns
    col1, col2, col3 = st.columns([1, 8, 1])
    with col1:
        if st.button("⬅️"):
            st.session_state['map_index'] = (idx - 1) % len(urutan_peta)
            st.rerun()
    with col2:
        st.write(f"<h5 style='text-align: center;'>Menampilkan layer: {param_aktif}</h5>", unsafe_allow_html=True)
    with col3:
        if st.button("➡️"):
            st.session_state['map_index'] = (idx + 1) % len(urutan_peta)
            st.rerun()

    # Render Peta
    peta_html = buat_peta_spesifik(df, param_aktif, data_daerah)
    st_folium(peta_html, width=1000, height=500)