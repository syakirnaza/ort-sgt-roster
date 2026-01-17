import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date
import random

# --- 1. HELPER FUNCTIONS ---
def get_sheet_url(sheet_id, sheet_name):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

@st.cache_data(ttl=60)
def load_all_data(sheet_id):
    try:
        staff_df = pd.read_csv(get_sheet_url(sheet_id, "StaffList"))
        leave_df = pd.read_csv(get_sheet_url(sheet_id, "LeaveRequest"))
        config_df = pd.read_csv(get_sheet_url(sheet_id, "Configuration"))
        
        # Clean headers & print for debugging
        for df in [staff_df, leave_df, config_df]:
            df.columns = df.columns.str.strip().str.replace(' ', '_')
            
        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str).strip() == "": return None
            try:
                # Normalizes Jan_1_2026 format
                return pd.to_datetime(str(date_str).replace('_', ' ')).date()
            except:
                return None

        leave_df['Date'] = leave_df['Date'].apply(parse_med_date)
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Data Loading Error: {e}")
        return None, None, None

# --- 2. ROSTER ENGINE ---
def generate_medical_roster(month, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [date(year, month, d) for d in range(1, num_days + 1)]
    
    # 1. Targeted Month Filtering
    current_month_str = f"{calendar.month_name[month][:3]}_{year}" 
    
    # Logic to handle missing Month_Year column safely
    if 'Month_Year' in config_df.columns:
        month_config = config_df[config_df['Month_Year'] == current_month_str]
    else:
        st.sidebar.warning(f"Header 'Month_Year' not found. Available: {list(config_df.columns)}")
        month_config = config_df
    
    # 2. Extract PH and OT Day Numbers
    def get_days_from_col(col_name):
        if col_name in month_config.columns:
            return pd.to_numeric(month_config[col_name], errors='coerce').dropna().astype(int).tolist()
        return []

    ph_days = get_days_from_col('PH_Dates')
    elot_days = get_days_from_col('ELOT_Dates')
    minor_ot_days = get_days_from_col('Minor_OT_Dates')
    
    all_staff = staff_df['Staff Name'].dropna().tolist()
    roster_output = []
    passive_idx = 0
    weekend_groups = {} 

    for day in days:
        d_num = day.day
        is_weekend = day.weekday() >= 5
        is_ph = d_num in ph_days
        is_special = is_weekend or is_ph
        
        # Filter availability
        daily_leave = leave_df[leave_df['Date'] == day]
        staff_absent = daily_leave['Name'].tolist() if 'Name' in daily_leave.columns else []
        staff_no_oncall = []
        if 'Oncall' in daily_leave.columns:
            staff_no_oncall = daily_leave[daily_leave['Oncall'] == 'No']['Name'].tolist()
        
        available = [s for s in all_staff if s not in staff_absent and s not in staff_no_oncall]
        
        row = {
            "Date": day, "Day": day.strftime("%A"),
            "Type": "Holiday/Weekend" if is_special else "Weekday",
            "Oncall_1": "SHORTAGE", "Oncall_2": "SHORTAGE", "Oncall_3": "",
            "Passive": "", "ELOT_1": "", "ELOT_2": "", "Minor_OT_1": "", "Minor_OT_2": ""
        }

        if len(available) >= 2:
            week_num = day.isocalendar()[1]
            if is_weekend:
                if week_num not in weekend_groups:
                    random.shuffle(available)
                    weekend_groups[week_num] = available
                pool = [s for s in weekend_groups[week_num] if s in available]
            else:
                random.shuffle(available)
                pool = available

            if len(pool) >= 2:
                row["Oncall_1"], row["Oncall_2"] = pool[0], pool[1]
            if is_special and len(pool) >= 3:
                row["Oncall_3"] = pool[2]
            
            # Specific OT Logic based on your Config Tab numbers
            if d_num in elot_days or is_special:
                if len(pool) >= 5:
                    row["ELOT_1"], row["ELOT_2"] = pool[3], pool[4]
            if d_num in minor_ot_days or is_special:
                if len(pool) >= 7:
                    row["Minor_OT_1"], row["Minor_OT_2"] = pool[5], pool[6]

        # Passive distribution (Equal for everyone)
        avail_passive = [s for s in all_staff if s not in staff_absent]
        if avail_passive:
            row["Passive"] = avail_passive[passive_idx % len(avail_passive)]
            passive_idx += 1

        roster_output.append(row)

    return pd.DataFrame(roster_output)

# --- 3. UI ---
st.set_page_config(page_title="MedRoster 2026", layout="wide")
st.title("🏥 Medical Specialist Roster")

MY_SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(MY_SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", list(calendar.month_name)[1:], index=0)
    m_idx = list(calendar.month_name).index(m_name)
    
    if st.button("Generate Roster"):
        df = generate_medical_roster(m_idx, 2026, staff, leave, config)
        st.dataframe(df, use_container_width=True)
        
        # Fairness Summary
        st.subheader("📊 Workload Summary")
        summary = df['Oncall_1'].value_counts().add(df['Oncall_2'].value_counts(), fill_value=0)
        st.bar_chart(summary)
