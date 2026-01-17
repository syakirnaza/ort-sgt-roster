import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Medical Master Roster 2026")

# --- 1. SESSION STATE INITIALIZATION ---
# This ensures your settings stay saved even when switching tabs
if 'ph_dates' not in st.session_state:
    st.session_state.ph_dates = [1, 2] 
if 'elot_dates' not in st.session_state:
    st.session_state.elot_dates = [5, 9, 12, 13, 16, 23, 26, 27]
if 'minor_ot_dates' not in st.session_state:
    st.session_state.minor_ot_dates = [3, 4, 10, 11, 24, 25]
if 'leave_data' not in st.session_state:
    st.session_state.leave_data = pd.DataFrame(columns=["Staff Name", "Date", "Type"])

staff_names = ["Akram", "Syahmi", "Simon", "Aishah", "Syakir", "Lemuel", "Yoges", "Fatiha", "Aina", "Thivya", "Arif", "Hefiy", "Johnny"]

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["⚙️ Configuration", "🏥 Leave & Restrictions", "📅 Roster & Stats"])

# --- PAGE 1: CONFIGURATION (WITH SAVE BUTTON) ---
if page == "⚙️ Configuration":
    st.title("⚙️ Roster Settings (Feb 2026)")
    
    # Use a form to prevent auto-refresh on every click
    with st.form("config_form"):
        st.info("Select dates and click 'Save Settings' at the bottom.")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🇲🇾 Public Holidays")
            new_ph = st.multiselect("Select PH Dates", range(1, 29), default=st.session_state.ph_dates)
        with col2:
            st.subheader("🩺 ELOT Dates")
            new_elot = st.multiselect("Select ELOT Dates", range(1, 29), default=st.session_state.elot_dates)
        with col3:
            st.subheader("✂️ Minor OT Dates")
            new_minor = st.multiselect("Select Minor OT Dates", range(1, 29), default=st.session_state.minor_ot_dates)
        
        submitted = st.form_submit_button("💾 Save & Apply Settings")
        if submitted:
            st.session_state.ph_dates = new_ph
            st.session_state.elot_dates = new_elot
            st.session_state.minor_ot_dates = new_minor
            st.success("Configuration updated successfully!")

# --- PAGE 2: LEAVE & RESTRICTIONS (WITH SAVE BUTTON) ---
elif page == "🏥 Leave & Restrictions":
    st.title("🏥 Staff Leave & Restrictions")
    
    with st.form("leave_form"):
        st.write("Manage staff requests here.")
        # Data editor inside a form
        updated_leave = st.data_editor(
            st.session_state.leave_data,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Staff Name": st.column_config.SelectboxColumn("Staff Name", options=staff_names, required=True),
                "Date": st.column_config.NumberColumn("Date (1-28)", min_value=1, max_value=28, format="%d", required=True),
                "Type": st.column_config.SelectboxColumn("Type", options=["Leave", "No Oncall"], required=True)
            }
        )
        
        save_leave = st.form_submit_button("💾 Save Leave Requests")
        if save_leave:
            st.session_state.leave_data = updated_leave
            st.success("All leave and restrictions saved!")

# --- PAGE 3: ROSTER & STATS ---
else:
    st.title("📅 Master Roster Dashboard (Feb 2026)")
    
    # Check if we have data to run
    if not st.session_state.ph_dates and not st.session_state.elot_dates:
        st.warning("Please configure your dates in the 'Configuration' tab first.")
    
    dates = pd.date_range(start="2026-02-01", periods=28)

    # [Roster generation logic remains the same as previous version]
    def generate_master_roster():
        df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
        cols = ["1st Call", "2nd Call", "3rd Call", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2"]
        for c in cols: df[c] = "-"

        for i in range(len(df)):
            d_val = df.loc[i, "Date"]
            is_special = df.loc[i, "Day"] in ['Saturday', 'Sunday'] or d_val in st.session_state.ph_dates
            
            def get_available(date, slot_type, exclude_list):
                for name in staff_names:
                    if name in exclude_list: continue
                    reqs = st.session_state.leave_data[
                        (st.session_state.leave_data["Staff Name"] == name) & 
                        (st.session_state.leave_data["Date"] == date)
                    ]
                    if not reqs.empty:
                        req_type = reqs.iloc[0]["Type"]
                        if req_type == "Leave": continue 
                        if req_type == "No Oncall" and slot_type != "Minor OT": continue 
                    return name
                return "UNASSIGNED"

            if d_val in st.session_state.minor_ot_dates:
                df.loc[i, "Minor OT 1"] = get_available(d_val, "Minor OT", [])
                df.loc[i, "Minor OT 2"] = get_available(d_val, "Minor OT", [df.loc[i, "Minor OT 1"]])

            if d_val in st.session_state.elot_dates:
                df.loc[i, "ELOT 1"] = get_available(d_val, "ELOT", [df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"]])
                df.loc[i, "ELOT 2"] = get_available(d_val, "ELOT", [df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"], df.loc[i, "ELOT 1"]])

            assigned_today = [df.loc[i, "ELOT 1"], df.loc[i, "ELOT 2"], df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"]]
            df.loc[i, "1st Call"] = get_available(d_val, "Call", assigned_today)
            assigned_today.append(df.loc[i, "1st Call"])
            df.loc[i, "2nd Call"] = get_available(d_val, "Call", assigned_today)
            
            if is_special:
                assigned_today.append(df.loc[i, "2nd Call"])
                df.loc[i, "3rd Call"] = get_available(d_val, "Call", assigned_today)
            else:
                assigned_today.append(df.loc[i, "2nd Call"])
                df.loc[i, "Passive"] = get_available(d_val, "Call", assigned_today)
        return df

    df_roster = generate_master_roster()

    def style_weekend(row):
        is_special = row.Day in ['Saturday', 'Sunday'] or row.Date in st.session_state.ph_dates
        if is_special:
            return ['background-color: #27ae60; color: black; font-weight: bold; border: 1px solid black;'] * len(row)
        return [''] * len(row)

    st.dataframe(df_roster.style.apply(style_weekend, axis=1), height=1000, use_container_width=True)

    # --- STATISTICS SECTION ---
    st.divider()
    st.subheader("📊 Staff Workload Distribution")
    # ... (Stats table logic remains the same)
