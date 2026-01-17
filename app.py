import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Medical Master Roster 2026")

# --- 1. SESSION STATE INITIALIZATION ---
if 'ph_dates' not in st.session_state:
    st.session_state.ph_dates = [1, 2] 
if 'elot_dates' not in st.session_state:
    st.session_state.elot_dates = [5, 9, 12, 13, 16, 23, 26, 27]
if 'minor_ot_dates' not in st.session_state:
    st.session_state.minor_ot_dates = [3, 4, 10, 11, 24, 25]

# New Structure: Dictionary where Key is Date, Value is list of names
if 'leave_map' not in st.session_state:
    st.session_state.leave_map = {i: [] for i in range(1, 29)}
if 'no_oncall_map' not in st.session_state:
    st.session_state.no_oncall_map = {i: [] for i in range(1, 29)}

staff_names = ["Akram", "Syahmi", "Simon", "Aishah", "Syakir", "Lemuel", "Yoges", "Fatiha", "Aina", "Thivya", "Arif", "Hefiy", "Johnny"]

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["⚙️ Configuration", "🏥 Leave & Restrictions", "📅 Roster & Stats"])

# --- PAGE 1: CONFIGURATION ---
if page == "⚙️ Configuration":
    st.title("⚙️ Roster Settings (Feb 2026)")
    with st.form("config_form"):
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
        if st.form_submit_button("💾 Save Settings"):
            st.session_state.ph_dates = new_ph
            st.session_state.elot_dates = new_elot
            st.session_state.minor_ot_dates = new_minor
            st.success("Configuration updated!")

# --- PAGE 2: LEAVE & RESTRICTIONS (NEW COLUMN LAYOUT) ---
elif page == "🏥 Leave & Restrictions":
    st.title("🏥 Daily Staff Restrictions")
    st.info("Fill in the names for each day and click 'Save All Requests'.")
    
    with st.form("leave_form"):
        # Create a display table for editing
        edit_cols = st.columns([1, 4, 4])
        edit_cols[0].write("**Date**")
        edit_cols[1].write("**Staff on Leave** (Full Absence)")
        edit_cols[2].write("**No Oncall Staff** (Minor OT Only)")
        
        temp_leave = {}
        temp_no_oncall = {}
        
        for i in range(1, 29):
            c1, c2, c3 = st.columns([1, 4, 4])
            c1.write(f"**Day {i}**")
            temp_leave[i] = c2.multiselect(f"Leave Day {i}", staff_names, default=st.session_state.leave_map[i], key=f"L{i}", label_visibility="collapsed")
            temp_no_oncall[i] = c3.multiselect(f"No OC Day {i}", staff_names, default=st.session_state.no_oncall_map[i], key=f"N{i}", label_visibility="collapsed")
        
        if st.form_submit_button("💾 Save All Requests"):
            st.session_state.leave_map = temp_leave
            st.session_state.no_oncall_map = temp_no_oncall
            st.success("Leave & Restrictions saved!")

# --- PAGE 3: ROSTER & STATS ---
else:
    st.title("📅 Master Roster Dashboard (Feb 2026)")
    dates = pd.date_range(start="2026-02-01", periods=28)

    def generate_master_roster():
        df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
        cols = ["1st Call", "2nd Call", "3rd Call", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2"]
        for c in cols: df[c] = "-"

        for i in range(len(df)):
            d_val = df.loc[i, "Date"]
            is_special = df.loc[i, "Day"] in ['Saturday', 'Sunday'] or d_val in st.session_state.ph_dates
            
            # Logic to find next available staff
            def get_next_available(date, slot_type, exclude_list):
                # We rotate the staff list based on the day to ensure fair distribution
                rotated_staff = staff_names[i % len(staff_names):] + staff_names[:i % len(staff_names)]
                for name in rotated_staff:
                    if name in exclude_list: continue
                    # Check Leave Map
                    if name in st.session_state.leave_map[date]: continue
                    # Check No Oncall Map
                    if name in st.session_state.no_oncall_map[date] and slot_type != "Minor OT": continue
                    return name
                return "UNASSIGNED"

            # 1. Assign Clinical Slots first
            if d_val in st.session_state.minor_ot_dates:
                df.loc[i, "Minor OT 1"] = get_next_available(d_val, "Minor OT", [])
                df.loc[i, "Minor OT 2"] = get_next_available(d_val, "Minor OT", [df.loc[i, "Minor OT 1"]])

            if d_val in st.session_state.elot_dates:
                df.loc[i, "ELOT 1"] = get_next_available(d_val, "ELOT", [df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"]])
                df.loc[i, "ELOT 2"] = get_next_available(d_val, "ELOT", [df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"], df.loc[i, "ELOT 1"]])

            # 2. Assign Call Slots
            assigned_today = [df.loc[i, "ELOT 1"], df.loc[i, "ELOT 2"], df.loc[i, "Minor OT 1"], df.loc[i, "Minor OT 2"]]
            df.loc[i, "1st Call"] = get_next_available(d_val, "Call", assigned_today)
            assigned_today.append(df.loc[i, "1st Call"])
            df.loc[i, "2nd Call"] = get_next_available(d_val, "Call", assigned_today)
            
            if is_special:
                assigned_today.append(df.loc[i, "2nd Call"])
                df.loc[i, "3rd Call"] = get_next_available(d_val, "Call", assigned_today)
            else:
                assigned_today.append(df.loc[i, "2nd Call"])
                df.loc[i, "Passive"] = get_next_available(d_val, "Call", assigned_today)
        return df

    df_roster = generate_master_roster()

    def style_special(row):
        is_special = row.Day in ['Saturday', 'Sunday'] or row.Date in st.session_state.ph_dates
        if is_special:
            return ['background-color: #27ae60; color: black; font-weight: bold; border: 1px solid black;'] * len(row)
        return [''] * len(row)

    st.dataframe(df_roster.style.apply(style_special, axis=1), height=1000, use_container_width=True)

    # --- STATS TABLE ---
    st.divider()
    st.subheader("📊 Staff Workload Distribution")
    stats = []
    for name in staff_names:
        c1 = (df_roster["1st Call"] == name).sum()
        c2 = (df_roster["2nd Call"] == name).sum()
        c3 = (df_roster["3rd Call"] == name).sum()
        stats.append({"Staff Name": name, "Oncall 1": c1, "Oncall 2": c2, "Oncall 3": c3, "Total Active": c1+c2+c3})
    st.table(pd.DataFrame(stats))
