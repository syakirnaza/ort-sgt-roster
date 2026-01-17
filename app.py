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
        staff_df = pd.read_csv(get_sheet_url(sheet_id, "StaffList")).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        leave_df = pd.read_csv(get_sheet_url(sheet_id, "LeaveRequest")).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        config_df = pd.read_csv(get_sheet_url(sheet_id, "Configuration")).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        
        staff_df.columns = staff_df.columns.str.strip()
        leave_df.columns = leave_df.columns.str.strip()
        config_df.columns = config_df.columns.str.strip()

        def parse_med_date(date_str):
            if pd.isna(date_str) or str(date_str) == "": return None
            return pd.to_datetime(str(date_str).replace('_', ' ')).date()

        leave_df['Date'] = leave_df['Date'].apply(parse_med_date)
        config_df['PH_Dates'] = config_df['PH_Dates'].apply(parse_med_date)
        
        return staff_df, leave_df.dropna(subset=['Date']), config_df.dropna(subset=['PH_Dates'])
    except Exception as e:
        st.error(f"Data Error: {e}")
        return None, None, None

# --- 2. THE ROSTER ENGINE ---
def generate_medical_roster(month, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
    ph_dates = config_df['PH_Dates'].tolist()
    
    # Staff Lists by Speciality/Eligibility
    all_staff = staff_df['Staff Name'].tolist()
    passive_pool = staff_df['Staff Name'].tolist() # Everyone gets passive
    
    roster_output = []
    
    # Trackers for Fairness
    passive_idx = 0
    
    for day in days:
        is_weekend = day.weekday() >= 5
        is_ph = day in ph_dates
        is_special = is_weekend or is_ph
        
        # 1. Filter Out Leave / No-Oncall
        daily_leave = leave_df[leave_df['Date'] == day]
        on_leave = daily_leave['Leave'].dropna().tolist()
        opted_out_oncall = daily_leave[daily_leave['Oncall'] == 'No']['Leave'].tolist() # Assuming names are in 'Leave' column
        
        def get_available(pool):
            return [s for s in pool if s not in on_leave and s not in opted_out_oncall]

        available_staff = get_available(all_staff)
        
        # --- ASSIGNMENT LOGIC ---
        daily_assignments = {
            "Date": day,
            "Day": day.strftime("%A"),
            "Type": "PH/Weekend" if is_special else "Weekday",
            "Oncall 1": "SHORTAGE",
            "Oncall 2": "SHORTAGE",
            "Oncall 3": "",
            "Passive": "",
            "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": ""
        }

        if len(available_staff) >= 2:
            # Shuffle available for basic randomness to avoid double-days
            random.shuffle(available_staff)
            daily_assignments["Oncall 1"] = available_staff[0]
            daily_assignments["Oncall 2"] = available_staff[1]
            
            # Weekend/PH Rules
            if is_special:
                if len(available_staff) >= 3:
                    daily_assignments["Oncall 3"] = available_staff[2]
                
                # Assign OT Staff (Rules require these on Special Days)
                ot_pool = available_staff[3:] if len(available_staff) > 3 else available_staff
                if len(ot_pool) >= 4:
                    daily_assignments["ELOT 1"] = ot_pool[0]
                    daily_assignments["ELOT 2"] = ot_pool[1]
                    daily_assignments["Minor OT 1"] = ot_pool[2]
                    daily_assignments["Minor OT 2"] = ot_pool[3]

        # Passive Allocation (Equally Distributed, independent of Oncall status)
        avail_passive = [s for s in passive_pool if s not in on_leave]
        if avail_passive:
            daily_assignments["Passive"] = avail_passive[passive_idx % len(avail_passive)]
            passive_idx += 1

        roster_output.append(daily_assignments)

    return pd.DataFrame(roster_output)

# --- 3. UI ---
st.title("🏥 Specialist Medical Roster Engine")
MY_SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

staff, leave, config = load_all_data(MY_SHEET_ID)

if staff is not None:
    st.sidebar.header("Roster Parameters")
    m_name = st.sidebar.selectbox("Month", list(calendar.month_name)[1:], index=datetime.now().month-1)
    m_idx = list(calendar.month_name).index(m_name)
    
    if st.button("Generate Roster with Rules"):
        final_roster = generate_medical_roster(m_idx, 2026, staff, leave, config)
        
        # Displaying with logic-based styling
        def highlight_special(row):
            color = '#fff0f0' if row.Type == "PH/Weekend" else ''
            return [f'background-color: {color}'] * len(row)

        st.subheader(f"Schedule for {m_name} 2026")
        st.dataframe(final_roster.style.apply(highlight_special, axis=1), use_container_width=True)
        
        # Download
        csv = final_roster.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Roster", csv, f"Roster_{m_name}.csv", "text/csv")
