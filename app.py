import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import calendar

# --- 1. SECURE CONNECTION LOGIC ---
def get_data_from_google(sheet_id, range_name):
    # Pull credentials from Streamlit Secrets
    creds_dict = st.secrets["connections"]["gsheets"]
    creds = service_account.Credentials.from_service_account_info(creds_dict)
    service = build('sheets', 'v4', credentials=creds)
    
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get('values', [])
    
    if not values:
        return pd.DataFrame()
    return pd.DataFrame(values[1:], columns=values[0])

# --- 2. LOAD DATA ---
# Replace this with your actual Sheet ID from the URL
SHEET_ID = st.secrets["connections"]["gsheets"]["spreadsheet_id"]

try:
    staff_df = get_data_from_google(SHEET_ID, "StaffList!A:Z")
    config_df = get_data_from_google(SHEET_ID, "Configuration!A:Z")
    leave_df = get_data_from_google(SHEET_ID, "LeaveRequest!A:Z")
    st.success("Connected via Official Google API!")
except Exception as e:
    st.error(f"Connection failed: {e}")
    st.stop()

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("📅 Roster Control")
selected_year = st.sidebar.selectbox("Year", [2025, 2026, 2027], index=1)
selected_month_name = st.sidebar.selectbox("Month", calendar.month_name[1:])
selected_month_num = list(calendar.month_name).index(selected_month_name)

# Dynamic Calendar Logic
num_days = calendar.monthrange(selected_year, selected_month_num)[1]
dates = pd.date_range(start=f"{selected_year}-{selected_month_num:02d}-01", periods=num_days)

# --- 3. EXTRACT MONTHLY SETTINGS ---
month_key = f"{selected_month_name}_{selected_year}"
month_config = config_df[config_df['Month_Year'] == month_key]

if not month_config.empty:
    def parse_dates(val):
        if pd.isna(val) or val == "": return []
        return [int(x.strip()) for x in str(val).split(',') if x.strip().isdigit()]
    
    ph_dates = parse_dates(month_config.iloc[0]['PH_Dates'])
    elot_dates = parse_dates(month_config.iloc[0]['ELOT_Dates'])
    minor_dates = parse_dates(month_config.iloc[0]['Minor_OT_Dates'])
else:
    ph_dates, elot_dates, minor_dates = [], [], []

# --- 4. ROSTER GENERATION LOGIC ---
def generate_roster():
    df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
    
    # Your specified headers
    columns = ["1st call", "2nd call", "3rd call", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2", "Wound Clinic"]
    for col in columns: df[col] = "-"

    # Simplified Assignment Logic
    for i in range(len(df)):
        d_num = df.loc[i, "Date"]
        d_name = df.loc[i, "Day"]
        date_key = f"{selected_month_name[:3]}_{d_num}_{selected_year}" # e.g. Jan_1_2026
        
        # Get Leave for this specific day
        daily_leave = leave_df[leave_df['Date_Key'] == date_key]
        staff_on_leave = []
        no_oncall = []
        
        if not daily_leave.empty:
            staff_on_leave = [x.strip() for x in str(daily_leave.iloc[0]['Staff_on_Leave']).split(',') if x.strip()]
            no_oncall = [x.strip() for x in str(daily_leave.iloc[0]['No_Oncall_Staff']).split(',') if x.strip()]

        # Filling slots based on your staff_df permissions
        assigned_today = []
        
        for col in columns:
            # Special logic: Only fill ELOT/Minor OT if date is in config
            if "ELOT" in col and d_num not in elot_dates: continue
            if "Minor OT" in col and d_num not in minor_dates: continue
            if col == "3rd call" and (d_name not in ['Saturday', 'Sunday'] and d_num not in ph_dates): continue

            # Filter staff who: 1. Can do the role, 2. Not on leave, 3. Not assigned today
            eligible = staff_df[
                (staff_df[col] == "Yes") & 
                (~staff_df['Staff Name'].isin(staff_on_leave)) &
                (~staff_df['Staff Name'].isin(assigned_today))
            ]
            
            # Additional check for No_Oncall_Staff (Restrictions)
            if "call" in col.lower() or "Passive" in col:
                eligible = eligible[~eligible['Staff Name'].isin(no_oncall)]

            if not eligible.empty:
                chosen = eligible.sample(1).iloc[0]['Staff Name']
                df.at[i, col] = chosen
                assigned_today.append(chosen)

    return df

# --- 5. DISPLAY ---
st.title(f"🏥 Medical Roster: {selected_month_name} {selected_year}")

tab1, tab2 = st.tabs(["📅 View Roster", "👥 Staff Permissions"])

with tab1:
    if st.button("🔄 Regenerate Roster"):
        st.cache_data.clear()
        
    final_df = generate_roster()
    
    # Styling for PH and Weekends (Green)
    def style_row(row):
        if row.Day in ['Saturday', 'Sunday'] or row.Date in ph_dates:
            return ['background-color: #d1f2eb; color: black; border: 1px solid #7fb3d5; font-weight: bold;'] * len(row)
        return [''] * len(row)

    st.dataframe(final_df.style.apply(style_row, axis=1), height=800, use_container_width=True)

with tab2:
    st.subheader("Current Staff Permissions (from StaffList)")
    st.dataframe(staff_df, use_container_width=True)
