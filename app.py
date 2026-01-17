import streamlit as st
import pandas as pd
import calendar
from datetime import datetime

# --- 1. HELPER FUNCTIONS ---

def get_sheet_url(sheet_id, sheet_name):
    """Generates the CSV export URL for specific Google Sheet tabs."""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

@st.cache_data(ttl=60)
def load_all_data(sheet_id):
    try:
        # Pull data from the 3 tabs using the Public Link method
        staff_df = pd.read_csv(get_sheet_url(sheet_id, "StaffList"))
        leave_df = pd.read_csv(get_sheet_url(sheet_id, "LeaveRequest"))
        config_df = pd.read_csv(get_sheet_url(sheet_id, "Configuration"))
        
        # Clean headers (removes invisible spaces or accidental newlines)
        staff_df.columns = staff_df.columns.str.strip()
        leave_df.columns = leave_df.columns.str.strip()
        config_df.columns = config_df.columns.str.strip()

        # Custom Parser for "Jan_1_2026" or "01_01_2026" format
        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str).strip() == "":
                return None
            # Replace underscores with spaces so pandas can read the string
            clean_str = str(date_str).replace('_', ' ')
            try:
                return pd.to_datetime(clean_str).date()
            except:
                return None

        # Process Dates in Leave tab (Header: 'Date')
        if 'Date' in leave_df.columns:
            leave_df['Date'] = leave_df['Date'].apply(parse_med_date)
            leave_df = leave_df.dropna(subset=['Date'])
            
        # Process Dates in Configuration tab (Header: 'PH_Dates')
        if 'PH_Dates' in config_df.columns:
            config_df['PH_Dates'] = config_df['PH_Dates'].apply(parse_med_date)
            config_df = config_df.dropna(subset=['PH_Dates'])

        return staff_df, leave_df, config_df
    except Exception as e:
        st.error(f"Critical Data Error: {e}")
        return None, None, None

# --- 2. ROSTER GENERATION LOGIC ---

def generate_roster(month, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
    
    # Staff list from 'Staff Name' column
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    # Public Holidays list
    ph_dates = config_df['PH_Dates'].tolist() if 'PH_Dates' in config_df.columns else []

    roster_list = []
    for i, day in enumerate(days):
        is_weekend = day.weekday() >= 5
        is_ph = day in ph_dates
        
        # Check leave for this day (Header: 'Date' and 'Leave')
        on_leave_today = leave_df[leave_df['Date'] == day]
        staff_absent = on_leave_today['Leave'].dropna().tolist() 
        
        # Filter available staff
        available = [s for s in all_staff if s not in staff_absent]
        
        # Simple rotation for assignment
        assigned = "SHORTAGE"
        if available:
            assigned = available[i % len(available)]

        roster_list.append({
            "Date": day,
            "Day": day.strftime("%A"),
            "Type": "Holiday/Weekend" if (is_weekend or is_ph) else "Normal Day",
            "Assigned Staff": assigned,
            "Absences": ", ".join(staff_absent) if staff_absent else "None"
        })
        
    return pd.DataFrame(roster_list)

# --- 3. STREAMLIT UI ---

st.set_page_config(page_title="MedRoster 2026", layout="wide")
st.title("🏥 Medical Specialist Roster System")

# INTEGRATED SHEET ID
MY_SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

staff, leave, config = load_all_data(MY_SHEET_ID)

if staff is not None:
    # Sidebar for Month/Year selection
    st.sidebar.header("Roster Parameters")
    month_name = st.sidebar.selectbox("Select Month", list(calendar.month_name)[1:])
    target_month = list(calendar.month_name).index(month_name)
    target_year = 2026 # Defaulted to 2026 as per your requirement
    
    tab_gen, tab_data = st.tabs(["📅 Generate Roster", "📂 Source Data View"])
    
    with tab_gen:
        if st.button("Generate Monthly Schedule"):
            final_df = generate_roster(target_month, target_year, staff, leave, config)
            
            # Styling: Red background for Holidays and Weekends
            def highlight_holiday(row):
                return ['background-color: #ffeded' if row.Type == "Holiday/Weekend" else '' for _ in row]
            
            st.dataframe(final_df.style.apply(highlight_holiday, axis=1), use_container_width=True)
            
            # Export to CSV
            csv = final_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Roster as CSV", csv, f"roster_{month_name}_2026.csv", "text/csv")

    with tab_data:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Staff Database")
            st.dataframe(staff)
        with col2:
            st.subheader("Leave & Public Holidays")
            st.write("Processed Public Holidays:")
            st.write(config[['PH_Dates']] if 'PH_Dates' in config.columns else "No PH dates found.")
            st.write("Processed Leave Requests:")
            st.dataframe(leave)
else:
    st.warning("⚠️ Application could not load data. Please ensure the Google Sheet is shared as 'Anyone with the link can view'.")
