import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
from fpdf import FPDF

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

if "lang_choice" not in st.session_state:
    st.session_state.lang_choice = "English"

# --- TRANSLATION VARIABLES ---
if st.session_state.lang_choice == "English":
    t_header = "CATALOGUE OF TIMES"
    t_label = "LANGUAGE"
    t_clear_btn = "🔄 Clear"
    t_results_msg = "Results"
    t_no_results = "No Results Found"
    t_download_csv = "Download CSV"
    t_download_pdf = "Download PDF"
    t_filename_csv = "results.csv"
    t_filename_pdf = "spec_sheet.pdf"
else:
    t_header = "CATALOGO DE TIEMPOS"
    t_label = "IDIOMA"
    t_clear_btn = "🔄 Limpiar"
    t_results_msg = "Resultados"
    t_no_results = "No se encontraron resultados"
    t_download_csv = "Descargar CSV"
    t_download_pdf = "Descargar PDF"
    t_filename_csv = "resultados.csv"
    t_filename_pdf = "hoja_especificaciones.pdf"

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
    def update_language():
        st.session_state.lang_choice = st.session_state.ui_lang_radio

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

# --- 4. FULLY INDEPENDENT FILTERING LOGIC ---
try:
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

    def reset_filters():
        if "cat_key" in st.session_state: st.session_state.cat_key = "All"
        if "garment_key" in st.session_state: st.session_state.garment_key = "All"
        if "pos_key" in st.session_state: st.session_state.pos_key = "All"
        if "op_key" in st.session_state: st.session_state.op_key = "All"

    # --- GET OPTIONS FROM FULL DATAFRAME (STATIC LISTS) ---
    # This guarantees that the lists NEVER shrink, regardless of what you select.
    # This is the "Nuclear Option" for solving order dependency.
    
    def get_static_options(df_source, col_name):
        return ["All"] + sorted([x for x in df_source[col_name].unique() if x != ""])

    all_cats = get_static_options(df, "CATEGORY")
    all_garments = get_static_options(df, "GARMENT")
    all_positions = get_static_options(df, "POSITION")
    all_ops = get_static_options(df, "OPERATION")

    with st.container():
        c1, c2, c3, c4, c_reset = st.columns([3, 3, 3, 3, 1])

        # Dropdowns use the FULL lists (all_cats, etc.)
        with c1:
            sel_cat = st.selectbox(lbl_cat, all_cats, key="cat_key")
        with c2:
            sel_garment = st.selectbox(lbl_garment, all_garments, key="garment_key")
        with c3:
            sel_pos = st.selectbox(lbl_pos, all_positions, key="pos_key")
        with c4:
            sel_op = st.selectbox(lbl_op, all_ops, key="op_key")
        with c_reset:
            st.write("") 
            st.write("") 
            st.button(t_clear_btn, on_click=reset_filters)

    # --- APPLY FILTER ONLY TO RESULTS ---
    # The selection logic happens here, affecting only the Table, not the dropdowns.
    mask = pd.Series([True] * len(df))

    if sel_cat != "All":
        mask = mask & (df["CATEGORY"] == sel_cat)
    if sel_garment != "All":
        mask = mask & (df["GARMENT"] == sel_garment)
    if sel_pos != "All":
        mask = mask & (df["POSITION"] == sel_pos)
    if sel_op != "All":
        mask = mask & (df["OPERATION"] == sel_op)

    final_df = df[mask]

    # --- 5. PDF GENERATOR FUNCTION ---
    def create_pdf(dataframe, headers):
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # --- LOGO & HEADER SECTION ---
        pdf.set_font("Arial", "B", 24)
        pdf.cell(0, 10, "MAK", ln=True, align="L")
        
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, t_header, ln=True, align="C")
        
        pdf.ln(10)

        # --- TABLE ---
        pdf.set_font("Arial", "B", 10)
        col_names = [headers[0], headers[1], headers[2], headers[3], headers[4], headers[5]]
        widths = [45, 45, 90, 30, 25, 40]
        
        for i, h in enumerate(col_names):
            txt = str(h).encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(widths[i], 10, txt, border=1, align='C', fill=False)
        pdf.ln()

        pdf.set_font("Arial", "", 9)
        for _, row in dataframe.iterrows():
            data = [
                row[headers[0]], row[headers[1]], row[headers[2]], 
                row[headers[3]], row[headers[4]], row[headers[5]]
            ]
            
            max_height = 10
            for i, d in enumerate(data):
                txt = str(d).encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(widths[i], max_height, txt, border=1)
            pdf.ln()
            
        return pdf.output(dest='S').encode('latin-1')

    # --- 6. DISPLAY RESULTS & DOWNLOADS ---
    st.divider()
    
    if not final_df.empty:
        display_df = final_df.rename(columns={
            "GARMENT": lbl_garment, "POSITION": lbl_pos, "OPERATION": lbl_op,
            "MACHINE": lbl_mach, "TIME": lbl_time, "CATEGORY": lbl_cat
        })
        
        cols_order = [lbl_garment, lbl_pos, lbl_op, lbl_mach, lbl_time, lbl_cat]
        display_df = display_df[cols_order]
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.caption(f"{t_results_msg}: {len(final_df)}")

        # --- DOWNLOAD BUTTONS ---
        col_btns, col_spacer = st.columns([2, 10])
        
        with col_btns:
            # 1. CSV Button
            csv = display_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 {t_download_csv}",
                data=csv,
                file_name=t_filename_csv,
                mime='text/csv',
                use_container_width=True
            )
            
            # 2. PDF Button (Stacked below)
            pdf_bytes = create_pdf(display_df, cols_order)
            st.download_button(
                label=f"📄 {t_download_pdf}",
                data=pdf_bytes,
                file_name=t_filename_pdf,
                mime='application/pdf',
                use_container_width=True
            )

    else:
        st.info(t_no_results)

except Exception as e:
    st.error(f"An error occurred: {e}")
