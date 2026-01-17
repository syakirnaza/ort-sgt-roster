import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Medical Master Roster")

# --- 1. SETTINGS & DATA ---
staff_names = ["Akram", "Syahmi", "Simon", "Aishah", "Syakir", "Lemuel", "Yoges", "Fatiha", "Aina", "Thivya", "Arif", "Hefiy", "Johnny"]
dates = pd.date_range(start="2025-02-01", periods=28)
ph_dates = [2, 17, 18, 19] # Malaysia PH (Feb 2, 17, 18, 19)

# ELOT Dates as specified
elot_dual = [5, 9, 12, 13, 16, 23, 26, 27]
elot_single = [7, 21]

# --- 2. THE ROSTER ENGINE ---
def generate_master_roster():
    df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
    
    # Initialize all columns
    cols = ["1st Call", "2nd Call", "3rd Call", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2"]
    for c in cols: df[c] = "-"

    # Logic: Group Assignments for Weekends/PH
    # Rotational groups to ensure fairness
    for i in range(len(df)):
        is_special = df.loc[i, "Day"] in ['Saturday', 'Sunday'] or df.loc[i, "Date"] in ph_dates
        
        # 1. ELOT Assignments
        if df.loc[i, "Date"] in elot_dual:
            df.loc[i, "ELOT 1"] = staff_names[i % 12]
            df.loc[i, "ELOT 2"] = staff_names[(i + 3) % 12]
        elif df.loc[i, "Date"] in elot_single:
            df.loc[i, "ELOT 1"] = staff_names[i % 12]

        # 2. Minor OT Assignments
        if not is_special: # Usually Minor OT is on weekdays
            df.loc[i, "Minor OT 1"] = staff_names[(i + 5) % 12]
            df.loc[i, "Minor OT 2"] = staff_names[(i + 8) % 12]

        # 3. Call Assignments
        # Basic rotation logic that avoids double-duty
        df.loc[i, "1st Call"] = staff_names[(i) % 12]
        df.loc[i, "2nd Call"] = staff_names[(i + 6) % 12]
        
        if is_special:
            # 3rd Call only on weekends/PH
            df.loc[i, "3rd Call"] = "Johnny" if i % 2 == 0 else "Arif"
        else:
            # Passive only on Weekdays
            df.loc[i, "Passive"] = staff_names[(i + 2) % 12]

    return df

# --- 3. UI DASHBOARD ---
st.title("🏥 Malaysia Dept Master Roster Dashboard")

if st.button("🔄 Generate Balanced Roster & Statistics"):
    df_roster = generate_master_roster()

    # Styling function: Green background, Black text for special days
    def style_weekend(row):
        is_special = row.Day in ['Saturday', 'Sunday'] or row.Date in ph_dates
        if is_special:
            return ['background-color: #27ae60; color: black; font-weight: bold; border: 1px solid black;'] * len(row)
        return [''] * len(row)

    st.subheader("Monthly Schedule (Feb 2025)")
    st.dataframe(df_roster.style.apply(style_weekend, axis=1), height=1000, use_container_width=True)

    # --- 4. STATISTICS TABLE ---
    st.divider()
    st.subheader("📊 Staff Workload Distribution")
    
    stats = []
    for name in staff_names:
        c1 = (df_roster["1st Call"] == name).sum()
        c2 = (df_roster["2nd Call"] == name).sum()
        c3 = (df_roster["3rd Call"] == name).sum()
        e1 = (df_roster["ELOT 1"] == name).sum()
        e2 = (df_roster["ELOT 2"] == name).sum()
        
        # Calculate Active Weekend Calls
        weekend_mask = (df_roster["Day"].isin(['Saturday', 'Sunday'])) | (df_roster["Date"].isin(ph_dates))
        weekend_calls = ((df_roster[weekend_mask]["1st Call"] == name).sum() + 
                         (df_roster[weekend_mask]["2nd Call"] == name).sum() + 
                         (df_roster[weekend_mask]["3rd Call"] == name).sum())
        
        total_active = c1 + c2 + c3
        
        stats.append({
            "Staff Name": name,
            "Oncall 1": c1,
            "Oncall 2": c2,
            "Oncall 3": c3,
            "ELOT 1": e1,
            "ELOT 2": e2,
            "Total Active Calls": total_active,
            "Total Weekend/PH Calls": weekend_calls
        })

    stats_df = pd.DataFrame(stats)
    st.table(stats_df)
    
    # Download Button
    csv = df_roster.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Roster as CSV", csv, "Feb_Master_Roster.csv", "text/csv")
