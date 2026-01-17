import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Medical Master Roster")

# --- 1. SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["⚙️ Configuration", "📅 Roster & Stats"])

# Initialize session state for dates if they don't exist
if 'ph_dates' not in st.session_state:
    st.session_state.ph_dates = [2, 17, 18, 19]
if 'elot_dates' not in st.session_state:
    st.session_state.elot_dates = [5, 9, 12, 13, 16, 23, 26, 27]
if 'minor_ot_dates' not in st.session_state:
    st.session_state.minor_ot_dates = [3, 4, 10, 11, 24, 25]

# --- PAGE 1: CONFIGURATION ---
if page == "⚙️ Configuration":
    st.title("⚙️ Roster Settings")
    st.info("Select the dates for this month. The roster will update automatically in the next tab.")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("🇲🇾 Public Holidays")
        st.session_state.ph_dates = st.multiselect("Select PH Dates", range(1, 29), default=st.session_state.ph_dates)
        
    with col2:
        st.subheader("🩺 ELOT Dates")
        st.session_state.elot_dates = st.multiselect("Select ELOT Dates", range(1, 29), default=st.session_state.elot_dates)
        
    with col3:
        st.subheader("✂️ Minor OT Dates")
        st.session_state.minor_ot_dates = st.multiselect("Select Minor OT Dates", range(1, 29), default=st.session_state.minor_ot_dates)

    st.success("Settings Saved! Go to the 'Roster & Stats' tab to see the results.")

# --- PAGE 2: ROSTER & STATS ---
else:
    st.title("📅 Malaysia Dept Master Roster Dashboard")
    
    staff_names = ["Akram", "Syahmi", "Simon", "Aishah", "Syakir", "Lemuel", "Yoges", "Fatiha", "Aina", "Thivya", "Arif", "Hefiy", "Johnny"]
    dates = pd.date_range(start="2025-02-01", periods=28)

    def generate_master_roster():
        df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
        cols = ["1st Call", "2nd Call", "3rd Call", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2"]
        for c in cols: df[c] = "-"

        for i in range(len(df)):
            d_val = df.loc[i, "Date"]
            is_special = df.loc[i, "Day"] in ['Saturday', 'Sunday'] or d_val in st.session_state.ph_dates
            
            # 1. ELOT Assignments
            if d_val in st.session_state.elot_dates:
                df.loc[i, "ELOT 1"] = staff_names[i % 12]
                df.loc[i, "ELOT 2"] = staff_names[(i + 3) % 12]

            # 2. Minor OT Assignments
            if d_val in st.session_state.minor_ot_dates:
                df.loc[i, "Minor OT 1"] = staff_names[(i + 5) % 12]
                df.loc[i, "Minor OT 2"] = staff_names[(i + 8) % 12]

            # 3. Call Assignments
            df.loc[i, "1st Call"] = staff_names[(i) % 12]
            df.loc[i, "2nd Call"] = staff_names[(i + 6) % 12]
            
            if is_special:
                df.loc[i, "3rd Call"] = "Johnny" if i % 2 == 0 else "Arif"
            else:
                df.loc[i, "Passive"] = staff_names[(i + 2) % 12]
        return df

    df_roster = generate_master_roster()

    # Apply Style: Green Background, Black Text
    def style_weekend(row):
        is_special = row.Day in ['Saturday', 'Sunday'] or row.Date in st.session_state.ph_dates
        if is_special:
            return ['background-color: #27ae60; color: black; font-weight: bold; border: 1px solid black;'] * len(row)
        return [''] * len(row)

    st.dataframe(df_roster.style.apply(style_weekend, axis=1), height=1000, use_container_width=True)

    # STATISTICS TABLE
    st.divider()
    st.subheader("📊 Staff Workload Distribution")
    
    stats = []
    for name in staff_names:
        c1 = (df_roster["1st Call"] == name).sum()
        c2 = (df_roster["2nd Call"] == name).sum()
        c3 = (df_roster["3rd Call"] == name).sum()
        e1 = (df_roster["ELOT 1"] == name).sum()
        e2 = (df_roster["ELOT 2"] == name).sum()
        
        ph_mask = (df_roster["Day"].isin(['Saturday', 'Sunday'])) | (df_roster["Date"].isin(st.session_state.ph_dates))
        weekend_calls = ((df_roster[ph_mask]["1st Call"] == name).sum() + 
                         (df_roster[ph_mask]["2nd Call"] == name).sum() + 
                         (df_roster[ph_mask]["3rd Call"] == name).sum())
        
        stats.append({
            "Staff Name": name, "Oncall 1": c1, "Oncall 2": c2, "Oncall 3": c3,
            "ELOT 1": e1, "ELOT 2": e2, "Total Active": c1+c2+c3, "Weekend/PH": weekend_calls
        })

    st.table(pd.DataFrame(stats))
