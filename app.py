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
        
        # Clean headers: Remove spaces but keep the names as you provided
        for df in [staff_df, leave_df, config_df]:
            df.columns = df.columns.str.strip()
            
        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str).strip() == "": return None
            try:
                # Normalizes Jan_1_2026 format for Leave requests
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
    
    # 1. Targeted Month Filtering (Looking for 'Jan_2026' in 'Month' column)
    current_month_str = f"{calendar.month_name[month][:3]}_{year}" 
    month_config = config_df[config_df['Month'] == current_month_str]
    
    # 2. Extract PH and OT Day Numbers using your NEW headers
    def get_days(col_name):
        if col_name in month_config.columns:
            return pd.to_numeric(month_config[col_name], errors='coerce').dropna().astype(int).tolist()
        return []

    ph_days = get_days('PHDate')
    elot_days = get_days('ELOTDate')
    minor_ot_days = get_days('MinorOTDate')
    
    # 3. Specialty Eligibility (Filtering based on StaffList columns)
    def get_eligible(column_name):
        # Returns list of staff who have 'Yes' or a value in that specialty column
        if column_name in staff_df.columns:
            return staff_df[staff_df[column_name].notna()]['Staff Name'].tolist()
        return staff_df['Staff Name'].tolist() # Fallback to all staff

    pool_1st = get_eligible('1st call')
    pool_2nd = get_eligible('2nd call')
    pool_3rd = get_eligible('3rd call')
    pool_elot = get_eligible('ELOT 1')
    pool_minor = get_eligible('Minor OT 1')
    all_staff = staff_df['Staff Name'].dropna().tolist()

    roster_output = []
    passive_idx = 0
    weekend_groups = {} 

    for day in days:
        d_num = day.day
        is_weekend = day.weekday() >= 5
        is_ph = d_num in ph_days
        is_special = is_weekend or is_ph
        
        # Filter availability (Leave & No Oncall)
        daily_leave = leave_df[leave_df['Date'] == day]
        absent = daily_leave['Name'].tolist()
        no_oncall = daily_leave[daily_leave['Oncall'] == 'No']['Name'].tolist() if 'Oncall' in daily_leave.columns else []
        
        # Helper to get available staff for a specific specialty pool
        def get_avail(pool):
            return [s for s in pool if s not in absent and s not in no_oncall]

        row = {
            "Date": day, "Day": day.strftime("%A"),
            "Type": "Holiday/Weekend" if is_special else "Weekday",
            "Oncall_1": "SHORTAGE", "Oncall_2": "SHORTAGE", "Oncall_3": "",
            "Passive": "", "ELOT_1": "", "ELOT_2": "", "Minor_OT_1": "", "Minor_OT_2": ""
        }

        # --- Assignment Logic ---
        avail_1st = get_avail(pool_1st)
        avail_2nd = get_avail(pool_2nd)
        
        # Rule: Oncall 1 and 2 always required
        if avail_1st and avail_2nd:
            # Weekend Consistency: Group same people for Sat/Sun
            week_num = day.isocalendar()[1]
            if is_weekend:
                if week_num not in weekend_groups:
                    random.shuffle(avail_1st); random.shuffle(avail_2nd)
                    weekend_groups[week_num] = {'o1': avail_1st[0], 'o2': avail_2nd[0]}
                row["Oncall_1"] = weekend_groups[week_num]['o1'] if weekend_groups[week_num]['o1'] in avail_1st else "SHORTAGE"
                row["Oncall_2"] = weekend_groups[week_num]['o2'] if weekend_groups[week_num]['o2'] in avail_2nd else "SHORTAGE"
            else:
                row["Oncall_1"], row["Oncall_2"] = random.sample(avail_1st, 1)[0], random.sample(avail_2nd, 1)[0]

        # Rule: Oncall 3 for Weekend/PH only
        if is_special:
            avail_3rd = get_avail(pool_3rd)
            if avail_3rd: row["Oncall_3"] = random.choice(avail_3rd)

        # Rule: ELOT/Minor OT based on Config Tab OR Special Days
        if d_num in elot_days or is_special:
            avail_elot = get_avail(pool_elot)
            if len(avail_elot) >= 2: row["ELOT_1"], row["ELOT_2"] = random.sample(avail_elot, 2)

        if d_num in minor_ot_days or is_special:
            avail_minor = get_avail(pool_minor)
            if len(avail_minor) >= 2: row["Minor_OT_1"], row["Minor_OT_2"] = random.sample(avail_minor, 2)

        # Rule: Passive distribution (Equal for everyone)
        avail_passive = [s for s in all_staff if s not in absent]
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
        
        # Color coding for easier reading
        def color_type(val):
            color = '#ffeded' if val == "Holiday/Weekend" else ''
            return f'background-color: {color}'

        st.dataframe(df.style.applymap(color_type, subset=['Type']), use_container_width=True)
        
        # Download
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", csv, f"Roster_{m_name}_2026.csv", "text/csv")
