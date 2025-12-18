import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="MAK - CATALOGO", layout="wide")

# --- 2. DATA LOADER ---
@st.cache_data(ttl=60)
def load_data(language):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = None

    # --- AUTHENTICATION ---
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "credentials.json")
        if os.path.exists(json_path):
            creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
    except Exception:
        pass

    if creds is None:
        try:
            if "gcp_service_account" in st.secrets:
                creds_dict = st.secrets["gcp_service_account"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except:
            pass

    if creds is None:
        st.error("❌ Authentication Error: No credentials found.")
        return pd.DataFrame(), {}

    # --- CONNECT TO SHEET ---
    try:
        client = gspread.authorize(creds)
        sheet_key = "1Hd-NGFEKJudVRcinsnN7G8LUrtWg6bdk9xACs0tm_kc"
        sh = client.open_by_key(sheet_key) 
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return pd.DataFrame(), {}

    # --- SMART SHEET SELECTOR ---
    def get_sheet_by_name(sheet_obj, target_name):
        available_sheets = {s.title.strip().lower(): s for s in sheet_obj.worksheets()}
        target_clean = target_name.strip().lower()
        if target_clean in available_sheets:
            return available_sheets[target_clean]
        return None

    # --- CONFIGURATION BASED ON LANGUAGE ---
    if language == "English":
        target_sheet_name = "English"
        start_row_index = 2 
        col_map = {
            1: "TYPE OF GARMENT", 2: "POSITION", 3: "OPERATION",
            4: "MACHINE", 5: "TIME (Secs)", 6: "CATEGORY"
        }
    else: # Spanish
        target_sheet_name = "Spanish"
        start_row_index = 9 
        col_map = {
            1: "TIPO DE PRENDA", 2: "POSICION", 3: "OPERACION",
            4: "MAQUINA", 5: "TIEMPo", 6: "CATIGORIA"
        }

    # --- LOAD WORKSHEET ---
    worksheet = get_sheet_by_name(sh, target_sheet_name)
    
    if worksheet is None:
        st.error(f"❌ Error: Could not find sheet named '{target_sheet_name}'. Available sheets: {[s.title for s in sh.worksheets()]}")
        return pd.DataFrame(), {}

    # --- READ DATA ---
    raw_data = worksheet.get_all_values()

    if len(raw_data) > start_row_index:
        data_rows = raw_data[start_row_index:]
    else:
        st.warning(f"Sheet '{target_sheet_name}' seems empty.")
        return pd.DataFrame(), {}

    extracted_data = []
    for row in data_rows:
        if len(row) > 6:
            item = {
                "GARMENT": row[1].strip(), 
                "POSITION": row[2].strip(), 
                "OPERATION": row[3].strip(),
                "MACHINE": row[4].strip(), 
                "TIME": row[5].strip(), 
                "CATEGORY": row[6].strip()
            }
            if item["GARMENT"] != "" or item["OPERATION"] != "":
                extracted_data.append(item)

    return pd.DataFrame(extracted_data), col_map

# --- 3. UI LAYOUT & STATE MANAGEMENT ---

# Initialize session state for language SOURCE OF TRUTH
if "lang_choice" not in st.session_state:
    st.session_state.lang_choice = "English"

# --- TRANSLATION VARIABLES ---
if st.session_state.lang_choice == "English":
    t_header = "CATALOGUE OF TIMES"
    t_label = "LANGUAGE"
    t_clear_btn = "🔄 Clear"
    t_results_msg = "Results"
    t_no_results = "No Results Found"
else:
    t_header = "CATALOGO DE TIEMPOS"
    t_label = "IDIOMA"
    t_clear_btn = "🔄 Limpiar"
    t_results_msg = "Resultados"
    t_no_results = "No se encontraron resultados"

# Helper for the display text
def format_language_option(option):
    if st.session_state.lang_choice == "Spanish":
        return "Inglés" if option == "English" else "Español"
    else:
        return option

# --- HEADER LAYOUT ---
col_header_1, col_header_2 = st.columns([5, 1])

with col_header_1:
    st.markdown("## **MAK**") 
    st.markdown(f"#### {t_header}")

with col_header_2:
    # CALLBACK: Updates the Source of Truth immediately
    def update_language():
        st.session_state.lang_choice = st.session_state.ui_lang_radio

    # Force the index based on the saved state
    current_idx = 0 if st.session_state.lang_choice == "English" else 1

    st.radio(
        label=t_label,
        options=["English", "Spanish"],
        index=current_idx,         
        key="ui_lang_radio",       
        on_change=update_language, 
        horizontal=True, 
        format_func=format_language_option
    )

st.markdown("---")

# --- 4. SMART "ANY ORDER" FILTERING LOGIC ---
try:
    # Load data
    df, col_map = load_data(st.session_state.lang_choice)
    
    if df.empty:
        st.warning("No data found.")
        st.stop()

    lbl_garment = col_map[1]
    lbl_pos = col_map[2]
    lbl_op = col_map[3]
    lbl_cat = col_map[6]
    lbl_mach = col_map[4]
    lbl_time = col_map[5]

    # --- RESET CALLBACK ---
    def reset_filters():
        if "cat_key" in st.session_state: st.session_state.cat_key = "All"
        if "garment_key" in st.session_state: st.session_state.garment_key = "All"
        if "pos_key" in st.session_state: st.session_state.pos_key = "All"
        if "op_key" in st.session_state: st.session_state.op_key = "All"

    # --- CURRENT SELECTIONS ---
    # We grab the current value from session state, default to "All"
    sel_cat = st.session_state.get("cat_key", "All")
    sel_garment = st.session_state.get("garment_key", "All")
    sel_pos = st.session_state.get("pos_key", "All")
    sel_op = st.session_state.get("op_key", "All")

    # --- CALCULATE VALID OPTIONS (INTERSECTION) ---
    # This logic allows you to start from any filter. 
    # The available options for a dropdown are determined by the OTHER 3 dropdowns.
    
    # Base Masks
    m_cat = (df["CATEGORY"] == sel_cat) if sel_cat != "All" else pd.Series([True] * len(df))
    m_garment = (df["GARMENT"] == sel_garment) if sel_garment != "All" else pd.Series([True] * len(df))
    m_pos = (df["POSITION"] == sel_pos) if sel_pos != "All" else pd.Series([True] * len(df))
    m_op = (df["OPERATION"] == sel_op) if sel_op != "All" else pd.Series([True] * len(df))

    # Helper to get valid options + ensure current selection is kept
    def get_smart_options(df_source, col_name, current_val):
        opts = ["All"] + sorted([x for x in df_source[col_name].unique() if x != ""])
        # CRITICAL: If the current selection is NOT in the new list (because of filtering),
        # we must add it back to prevent the "Streamlit Reset" bug.
        if current_val != "All" and current_val not in opts:
            opts.append(current_val)
        return opts

    # 1. Available Categories (Filtered by Garment + Pos + Op)
    avail_cat = get_smart_options(df[m_garment & m_pos & m_op], "CATEGORY", sel_cat)

    # 2. Available Garments (Filtered by Cat + Pos + Op)
    avail_garment = get_smart_options(df[m_cat & m_pos & m_op], "GARMENT", sel_garment)

    # 3. Available Positions (Filtered by Cat + Garment + Op)
    avail_pos = get_smart_options(df[m_cat & m_garment & m_op], "POSITION", sel_pos)

    # 4. Available Operations (Filtered by Cat + Garment + Pos)
    avail_op = get_smart_options(df[m_cat & m_garment & m_pos], "OPERATION", sel_op)


    # --- RENDER UI ---
    with st.container():
        c1, c2, c3, c4, c_reset = st.columns([3, 3, 3, 3, 1])

        with c1:
            st.selectbox(lbl_cat, avail_cat, key="cat_key")

        with c2:
            st.selectbox(lbl_garment, avail_garment, key="garment_key")

        with c3:
            st.selectbox(lbl_pos, avail_pos, key="pos_key")

        with c4:
            st.selectbox(lbl_op, avail_op, key="op_key")
            
        with c_reset:
            st.write("") 
            st.write("") 
            st.button(t_clear_btn, on_click=reset_filters)

    # --- FINAL TABLE FILTER ---
    final_mask = m_cat & m_garment & m_pos & m_op
    final_df = df[final_mask]

    # --- 5. DISPLAY RESULTS ---
    st.divider()
    
    if not final_df.empty:
        display_df = final_df.rename(columns={
            "GARMENT": lbl_garment, "POSITION": lbl_pos, "OPERATION": lbl_op,
            "MACHINE": lbl_mach, "TIME": lbl_time, "CATEGORY": lbl_cat
        })
        
        cols_order = [lbl_garment, lbl_pos, lbl_op, lbl_mach, lbl_time, lbl_cat]
        
        st.dataframe(display_df[cols_order], use_container_width=True, hide_index=True)
        st.caption(f"{t_results_msg}: {len(final_df)}")
    else:
        st.info(t_no_results)

except Exception as e:
    st.error(f"An error occurred: {e}")
