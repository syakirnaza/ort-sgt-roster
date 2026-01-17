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
        
        for df in [staff_df, leave_df, config_df]:
            df.columns = df.columns.astype(str).str.strip()
            
        # Ensure Configuration Headers: Month, PHDate, ELOTDate, MinorOTDate
        if len(config_df.columns) >= 4:
            config_df.columns = ['Month', 'PHDate', 'ELOTDate', 'MinorOTDate'] + list(config_df.columns[4:])

        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str).strip() == "": return None
            try:
                return pd.to_datetime(str(date_str).replace('_', ' ')).date()
            except:
                return None

        leave_df['Date'] = leave_df['Date'].apply(parse_med_date)
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Data Loading Error: {e}")
        return None, None, None

# --- 2. ROSTER ENGINE ---
def generate_medical_roster(month_idx, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month_idx)[1]
    days = [date(year, month_idx, d) for d in range(1, num_days + 1)]
    
    # 1. Targeted Month Filtering (Full name: e.g., 'January')
    target_month_name = calendar.month_name[month_idx]
    month_config = config_df[config_df['Month'].astype(str).str.strip() == target_month_name]
    
    # 2. Helper to parse comma-separated strings (e.g., "1, 29, 30")
    def get_list_from_cell(col_name):
        if col_name in month_config.columns and not month_config[col_name].empty:
            cell_val = str(month_config[col_name].iloc[0])
            if cell_val and cell_val != 'nan':
                # Split by comma, strip spaces, convert to int
                return [int(x.strip()) for x in cell_val.split(',') if x.strip().isdigit()]
        return []

    ph_days = get_list_from_cell('PHDate')
    elot_days = get_list_from_cell('ELOTDate')
    minor_ot_days = get_list_from_cell('MinorOTDate')
    
    # Eligibility Pools
    all_staff = staff_df['Staff Name'].dropna().tolist()
    def get_eligible(col):
        return staff_df[staff_df[col].notna()]['Staff Name'].tolist() if col in staff_df.columns else all_staff

    pool_1st = get_eligible('1st call')
    pool_2nd = get_eligible('2nd call')
    pool_3rd = get_eligible('3rd call')
    pool_elot = get_eligible('ELOT 1')
    pool_minor = get_eligible('Minor OT 1')

    roster_output = []
    passive_idx = 0
    weekend_groups = {} 

    for day in days:
        d_num = day.day
        is_weekend = day.weekday() >= 5
        is_ph = d_num in ph_days
        is_special = is_weekend or is_ph
        
        daily_leave = leave_df[leave_df['Date'] == day]
        absent = daily_leave['Name'].tolist()
        no_oncall = daily_leave[daily_leave['Oncall'] == 'No']['Name'].tolist() if 'Oncall' in daily_leave.columns else []
        
        def get_avail(pool):
            return [s for s in pool if s not in absent and s not in no_oncall]

        row = {
            "Date": day, "Day": day.strftime("%A"),
            "Type": "PH/Weekend" if is_special else "Weekday",
            "Oncall_1": "SHORTAGE", "Oncall_2": "SHORTAGE", "Oncall_3": "",
            "Passive": "", "ELOT_1": "", "ELOT_2": "", "Minor_OT_1": "", "Minor_OT_2": ""
        }

        # Assignment Logic
        a1, a2 = get_avail(pool_1st), get_avail(pool_2nd)
        if a1 and a2:
            week_num = day.isocalendar()[1]
            if is_weekend:
                if week_num not in weekend_groups:
                    random.shuffle(a1); random.shuffle(a2)
                    weekend_groups[week_num] = {'o1': a1[0], 'o2': a2[0]}
                row["Oncall_1"] = weekend_groups[week_num]['o1'] if weekend_groups[week_num]['o1'] in a1 else a1[0]
                row["Oncall_2"] = weekend_groups[week_num]['o2'] if weekend_groups[week_num]['o2'] in a2 else a2[0]
            else:
                row["Oncall_1"], row["Oncall_2"] = random.choice(a1), random.choice(a2)

        if is_special:
            a3 = get_avail(pool_3rd)
            if a3: row["Oncall_3"] = random.choice(a3)
            
            ae = get_avail(pool_elot)
            if len(ae) >= 2: row["ELOT_1"], row["ELOT_2"] = random.sample(ae, 2)
            
            am = get_avail(pool_minor)
            if len(am) >= 2: row["Minor_OT_1"], row["Minor_OT_2"] = random.sample(am, 2)
        else:
            # Check for weekday ELOT/Minor OT from config
            if d_num in elot_days:
                ae = get_avail(pool_elot)
                if len(ae) >= 2: row["ELOT_1"], row["ELOT_2"] = random.sample(ae, 2)
            if d_num in minor_ot_days:
                am = get_avail(pool_minor)
                if len(am) >= 2: row["Minor_OT_1"], row["Minor_OT_2"] = random.sample(am, 2)

        avail_passive = [s for s in all_staff if s not in absent]
        if avail_passive:
            row["Passive"] = avail_passive[passive_idx % len(avail_passive)]
            passive_idx += 1

        roster_output.append(row)

    return pd.DataFrame(roster_output)

# --- 3. MAIN ---
st.title("🏥 Medical Roster Generator 2026")
SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", list(calendar.month_name)[1:])
    m_idx = list(calendar.month_name).index(m_name)
    
    if st.button("Generate Roster"):
        df_final = generate_medical_roster(m_idx, 2026, staff, leave, config)
        st.dataframe(df_final, use_container_width=True)
        
