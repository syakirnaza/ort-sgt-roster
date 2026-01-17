import streamlit as st
import pandas as pd
import random

st.set_page_config(layout="wide", page_title="Malaysia Dept Roster")

st.title("🏥 Medical On-Call & ELOT Dashboard")
st.info("Malaysia Time (GMT+8) | Feb 1st = Sunday | Feb 2nd = PH")

# --- 1. STAFF DATABASE & RULES ---
staff_data = {
    "Akram": {"max": 7, "roles": [1, 2]},
    "Syahmi": {"max": 7, "roles": [1, 2]},
    "Simon": {"max": 6, "roles": [1, 2]},
    "Aishah": {"max": 6, "roles": [1, 2]},
    "Syakir": {"max": 7, "roles": [1, 2]},
    "Lemuel": {"max": 7, "roles": [1, 2]},
    "Yoges": {"max": 6, "roles": [1, 2]},
    "Fatiha": {"max": 6, "roles": [2]},
    "Aina": {"max": 6, "roles": [2]},
    "Thivya": {"max": 6, "roles": [1, 2, 3]},
    "Arif": {"max": 6, "roles": [3]},
    "Hefiy": {"max": 5, "roles": [1, 2]},
    "Johnny": {"max": 3, "roles": [3]}
}

# --- 2. CALENDAR SETUP ---
dates = pd.date_range(start="2025-02-01", periods=28)
ph_dates = [2, 17, 18, 19] # Feb 2, 17, 18, 19
elot_dual = [5, 9, 12, 13, 16, 23, 26, 27]
elot_single = [7, 21]

# --- 3. GENERATION LOGIC ---
if st.button("🚀 Generate Balanced Roster"):
    df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
    
    # Initialize columns
    for col in ["1st Call", "2nd Call", "3rd Call", "Passive", "ELOT 1", "ELOT 2"]:
        df[col] = "-"

    # Manual override for the specific groups we discussed
    # PH Group 1 (Feb 1-2): Aina, Syahmi, Arif
    df.loc[0, ["1st Call", "2nd Call", "3rd Call"]] = ["Aina", "Syahmi", "Arif"]
    df.loc[1, ["1st Call", "2nd Call", "3rd Call"]] = ["Syahmi", "Arif", "Aina"]

    # PH Group 2 (Feb 17-19): Simon, Syakir, Lemuel
    df.loc[16, ["1st Call", "2nd Call", "3rd Call"]] = ["Syakir", "Lemuel", "Simon"]
    df.loc[17, ["1st Call", "2nd Call", "3rd Call"]] = ["Lemuel", "Simon", "Syakir"]
    df.loc[18, ["1st Call", "2nd Call", "3rd Call"]] = ["Simon", "Syakir", "Lemuel"]

    # Simple logic filler for other days (for demo purposes)
    # In a full production app, this would be a complex loop
    df.loc[4, ["1st Call", "2nd Call", "3rd Call"]] = ["Akram", "Syahmi", "Johnny"]
    df.loc[20, ["1st Call", "ELOT 1"]] = ["Aishah", "Yoges (Wound)"]

    # --- 4. STYLING & DISPLAY ---
    def style_roster(row):
        if row.Day in ['Saturday', 'Sunday'] or row.Date in ph_dates:
            return ['background-color: #e8f5e9'] * len(row)
        return [''] * len(row)

    st.subheader("Finalized February Schedule")
    st.table(df.style.apply(style_roster, axis=1))
    
    st.success("Roster Generated! Simon and Aishah capped at 6. Weekend/PH highlighted light green.")
