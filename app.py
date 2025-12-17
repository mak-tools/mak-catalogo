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

# --- 3. UI LAYOUT & TRANSLATIONS ---

# Initialize session state
if "lang_choice" not in st.session_state:
    st.session_state.lang_choice = "English"

# Define Text Variables
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

# Helper function to display the options correctly
def format_language_option(option):
    if st.session_state.lang_choice == "Spanish":
        return "Inglés" if option == "English" else "Español"
    else:
        return option

col_header_1, col_header_2 = st.columns([5, 1])

with col_header_1:
    st.markdown("## **MAK**") 
    st.markdown(f"#### {t_header}")

with col_header_2:
    # Use format_func to change how the options look without breaking the logic
    language = st.radio(
        t_label, 
        ["English", "Spanish"], 
        horizontal=True, 
        key="lang_choice",
        format_func=format_language_option
    )

st.markdown("---")

# --- 4. FILTERING LOGIC ---
try:
    df, col_map = load_data(language)
    
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
        st.session_state.cat_key = "All"
        st.session_state.garment_key = "All"
        st.session_state.pos_key = "All"
        st.session_state.op_key = "All"

    def get_sorted_options(dataframe, col_key):
        return ["All"] + sorted([x for x in dataframe[col_key].unique() if x != ""])

    with st.container():
        c1, c2, c3, c4, c_reset = st.columns([3, 3, 3, 3, 1])

        # 1. CATEGORY
        with c1:
            cat_opts = get_sorted_options(df, "CATEGORY")
            sel_cat = st.selectbox(lbl_cat, cat_opts, key="cat_key")
        
        if sel_cat != "All":
            df_step1 = df[df["CATEGORY"] == sel_cat]
        else:
            df_step1 = df

        # 2. GARMENT
        with c2:
            garment_opts = get_sorted_options(df_step1, "GARMENT")
            sel_garment = st.selectbox(lbl_garment, garment_opts, key="garment_key")

        if sel_garment != "All":
            df_step2 = df_step1[df_step1["GARMENT"] == sel_garment]
        else:
            df_step2 = df_step1

        # 3. POSITION
        with c3:
            pos_opts = get_sorted_options(df_step2, "POSITION")
            sel_pos = st.selectbox(lbl_pos, pos_opts, key="pos_key")

        if sel_pos != "All":
            df_step3 = df_step2[df_step2["POSITION"] == sel_pos]
        else:
            df_step3 = df_step2

        # 4. OPERATION
        with c4:
            op_opts = get_sorted_options(df_step3, "OPERATION")
            sel_op = st.selectbox(lbl_op, op_opts, key="op_key")

        if sel_op != "All":
            final_df = df_step3[df_step3["OPERATION"] == sel_op]
        else:
            final_df = df_step3
            
        # 5. DYNAMIC RESET BUTTON
        with c_reset:
            st.write("") 
            st.write("") 
            st.button(t_clear_btn, on_click=reset_filters)

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
