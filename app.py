import streamlit as st
import pandas as pd
import calendar
from datetime import datetime

# --- 1. CONFIGURATION & LOADING ---
st.set_page_config(page_title="Medical Roster 2026", layout="wide")
SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

def get_sheet_url(sheet_id, sheet_name):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

@st.cache_data(ttl=60)
def load_all_data():
    try:
        # Load the three tabs
        staff_df = pd.read_csv(get_sheet_url(SHEET_ID, "StaffList"))
        leave_df = pd.read_csv(get_sheet_url(SHEET_ID, "LeaveRequest"))
        config_df = pd.read_csv(get_sheet_url(SHEET_ID, "Configuration"))
        
        # Clean headers (strip spaces)
        staff_df.columns = staff_df.columns.str.strip()
        leave_df.columns = leave_df.columns.str.strip()
        config_df.columns = config_df.columns.str.strip()

        # Convert Date columns to actual dates
        # Note: We use the header 'Date' from your Leave Request tab
        leave_df['Date'] = pd.to_datetime(leave_df['Date']).dt.date
        
        return staff_df, leave_df, config_df
    except Exception as e:
        st.error(f"Mapping Error: Could not find header {e}. Please check Sheet names.")
        return None, None, None

# --- 2. ROSTER ENGINE ---
def generate_roster(month, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
    
    # Get staff list from your 'Staff Name' column
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    # Extract Public Holidays from Configuration if they exist
    ph_dates = []
    if 'PH_Dates' in config_df.columns:
        ph_dates = pd.to_datetime(config_df['PH_Dates']).dropna().dt.date.tolist()

    roster_results = []
    for i, day in enumerate(days):
        # Identify day type
        is_weekend = day.weekday() >= 5
        is_ph = day in ph_dates
        
        # Filter staff on leave or 'No Oncall'
        # Logic: Check LeaveRequest tab for this date
        today_leave = leave_df[leave_df['Date'] == day]
        staff_on_leave = today_leave['Leave'].dropna().tolist() # People with leave marked
        no_oncall = today_leave[today_leave['Oncall'] == 'No']['Date'].tolist() # People who opted out

        # Available pool
        available = [s for s in all_staff if s not in staff_on_leave]
        
        # Simple Assignment (Example: Primary On-Call)
        assigned = available[i % len(available)] if available else "MANPOWER SHORTAGE"

        roster_results.append({
            "Date": day,
            "Day": day.strftime("%A"),
            "Status": "PH/Weekend" if (is_weekend or is_ph) else "Normal",
            "On-Call Staff": assigned,
            "Leave/Notes": ", ".join(staff_on_leave) if staff_on_leave else ""
        })
    
    return pd.DataFrame(roster_results)

# --- 3. UI ---
st.title("🏥 Specialist Roster Generator")

staff, leave, config = load_all_data()

if staff is not None:
    # Sidebar mapping
    st.sidebar.header("Roster Settings")
    sel_month_name = st.sidebar.selectbox("Month", list(calendar.month_name)[1:])
    sel_month = list(calendar.month_name).index(sel_month_name)
    sel_year = st.sidebar.number_input("Year", value=2026)

    tab1, tab2, tab3 = st.tabs(["View Roster", "Staff Database", "Leave/PH Data"])

    with tab1:
        if st.button("Generate Roster"):
            df_roster = generate_roster(sel_month, sel_year, staff, leave, config)
            
            # Highlight Weekends and PH
            def style_rows(row):
                if row.Status == "PH/Weekend":
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)
            
            st.dataframe(df_roster.style.apply(style_rows, axis=1), use_container_width=True)
            
    with tab2:
        st.subheader("Staff Roles & Capabilities")
        st.write("Using headers: Staff Name, 1st call, 2nd call, etc.")
        st.dataframe(staff)

    with tab3:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Leave Requests")
            st.dataframe(leave)
        with col_b:
            st.subheader("Public Holidays (Configuration)")
            st.dataframe(config[['PH_Dates']].dropna())
