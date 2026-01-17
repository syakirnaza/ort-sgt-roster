import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
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
        
        staff_df.columns = staff_df.columns.str.strip()
        leave_df.columns = leave_df.columns.str.strip()
        config_df.columns = config_df.columns.str.strip()

        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str).strip() == "":
                return None
            
            d_str = str(date_str).strip()
            
            # Try specific format Jan_1_2026 first
            try:
                return datetime.strptime(d_str, "%b_%d_%Y").date()
            except:
                # Fallback for standard formats like 2026-01-01 or Jan 1 2026
                try:
                    clean_str = d_str.replace('_', ' ')
                    return pd.to_datetime(clean_str).date()
                except Exception as e:
                    return None

        leave_df['Date'] = leave_df['Date'].apply(parse_med_date)
        config_df['PH_Dates'] = config_df['PH_Dates'].apply(parse_med_date)
        
        return staff_df, leave_df.dropna(subset=['Date']), config_df.dropna(subset=['PH_Dates'])
    except Exception as e:
        st.error(f"Data Error: {e}")
        return None, None, None

# --- 2. THE ROSTER ENGINE (Updated with your Logic) ---
def generate_medical_roster(month, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
    ph_dates = config_df['PH_Dates'].tolist()
    
    all_staff = staff_df['Staff Name'].dropna().tolist()
    roster_output = []
    
    # We maintain an index for Passive rotation across the month
    passive_idx = 0
    
    # Logic for Weekend Groups: We want the same person for the whole weekend
    # We will pre-assign weekends to maintain consistency
    weekend_assignments = {} # Key: (Year, WeekNumber), Value: List of staff

    for day in days:
        is_weekend = day.weekday() >= 5
        is_ph = day in ph_dates
        is_special = is_weekend or is_ph
        
        # 1. Filter Out Leave / No-Oncall
        # In your sheet, 'Name' is in the 'Leave' column for LeaveRequest
        daily_leave_rows = leave_df[leave_df['Date'] == day]
        staff_on_leave = daily_leave_rows['Name'].dropna().tolist() if 'Name' in daily_leave_rows.columns else []
        staff_no_oncall = daily_leave_rows[daily_leave_rows['Oncall'] == 'No']['Name'].tolist() if 'Oncall' in daily_leave_rows.columns else []
        
        available = [s for s in all_staff if s not in staff_on_leave and s not in staff_no_oncall]
        
        daily_assignments = {
            "Date": day,
            "Day": day.strftime("%A"),
            "Type": "PH/Weekend" if is_special else "Weekday",
            "Oncall 1": "SHORTAGE", "Oncall 2": "SHORTAGE", "Oncall 3": "",
            "Passive": "", "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""
        }

        if len(available) >= 2:
            # Weekend Consistency Rule:
            week_num = day.isocalendar()[1]
            if is_weekend:
                if week_num not in weekend_assignments:
                    random.shuffle(available)
                    weekend_assignments[week_num] = available[:8] # Reserve a group for the weekend
                
                pool = [s for s in weekend_assignments[week_num] if s in available]
            else:
                random.shuffle(available)
                pool = available

            if len(pool) >= 2:
                daily_assignments["Oncall 1"] = pool[0]
                daily_assignments["Oncall 2"] = pool[1]
            
            if is_special and len(pool) >= 3:
                daily_assignments["Oncall 3"] = pool[2]
                
            if is_special and len(pool) >= 7:
                daily_assignments["ELOT 1"] = pool[3]
                daily_assignments["ELOT 2"] = pool[4]
                daily_assignments["Minor OT 1"] = pool[5]
                daily_assignments["Minor OT 2"] = pool[6]
        
        # Passive Allocation (Equal distribution)
        avail_passive = [s for s in all_staff if s not in staff_on_leave]
        if avail_passive:
            daily_assignments["Passive"] = avail_passive[passive_idx % len(avail_passive)]
            passive_idx += 1

        roster_output.append(daily_assignments)

    return pd.DataFrame(roster_output)

# --- 3. UI ---
st.title("🏥 Medical Specialist Roster - 2026")
MY_SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

staff, leave, config = load_all_data(MY_SHEET_ID)

if staff is not None:
    st.sidebar.header("Roster Parameters")
    m_name = st.sidebar.selectbox("Month", list(calendar.month_name)[1:], index=datetime.now().month-1)
    m_idx = list(calendar.month_name).index(m_name)
    
    if st.button("Generate Roster with Hard Rules"):
        final_roster = generate_medical_roster(m_idx, 2026, staff, leave, config)
        
        st.subheader(f"Schedule for {m_name} 2026")
        st.dataframe(final_roster, use_container_width=True)
        
        csv = final_roster.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Roster", csv, f"Roster_{m_name}.csv", "text/csv")
