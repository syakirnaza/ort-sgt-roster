import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date
import random

# --- 1. DATA LOADING ---
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
    
    target_month_name = calendar.month_name[month_idx]
    month_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month_name]
    
    def parse_csv_cell(df_row, col_idx):
        if not df_row.empty and len(df_row.columns) > col_idx:
            val = str(df_row.iloc[0, col_idx])
            if val and val != 'nan' and val.strip() != "":
                return [name.strip() for name in val.split(',')]
        return []

    def get_config_days(col_idx):
        if not month_config.empty and len(month_config.columns) > col_idx:
            val = str(month_config.iloc[0, col_idx])
            if val and val != 'nan' and val.strip() != "":
                return [int(x.strip()) for x in val.split(',') if x.strip().isdigit()]
        return []

    ph_days = get_config_days(1)
    elot_days = get_config_days(2)
    minor_ot_days = get_config_days(3)
    wound_days = get_config_days(4)
    
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    def get_eligible(col):
        return staff_df[staff_df[col].notna()]['Staff Name'].tolist() if col in staff_df.columns else all_staff

    pool_1st, pool_2nd, pool_3rd = get_eligible('1st call'), get_eligible('2nd call'), get_eligible('3rd call')
    pool_elot, pool_minor = get_eligible('ELOT 1'), get_eligible('Minor OT 1')
    pool_wound = get_eligible('Wound Clinic')

    roster_output = []
    violations = []
    passive_idx = 0
    weekend_groups = {} 

    for day in days:
        d_num = day.day
        is_weekend = day.weekday() >= 5
        is_sat = day.weekday() == 5
        is_ph = d_num in ph_days
        
        daily_leave_row = leave_df[leave_df['Date'] == day]
        absent = parse_csv_cell(daily_leave_row, 3) 
        no_oncall = parse_csv_cell(daily_leave_row, 4) 

        def get_avail(pool):
            return [s for s in pool if s not in absent and s not in no_oncall]

        row = {
            "Date": day, "Day": day.strftime("%A"),
            "Is_Special": (is_weekend or is_ph),
            "Oncall 1": "", "Oncall 2": "", "Oncall 3": "",
            "Passive": "", "ELOT 1": "", "ELOT 2": "", 
            "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""
        }

        # --- Oncall 1 & 2 ---
        a1, a2 = get_avail(pool_1st), get_avail(pool_2nd)
        if not a1: violations.append(f"Day {d_num}: No staff available for Oncall 1 (Pool empty or on leave)")
        if not a2: violations.append(f"Day {d_num}: No staff available for Oncall 2")
        
        if a1 and a2:
            week_num = day.isocalendar()[1]
            if is_weekend:
                if week_num not in weekend_groups:
                    random.shuffle(a1); random.shuffle(a2)
                    weekend_groups[week_num] = {'o1': a1[0], 'o2': a2[0]}
                
                # Check consistency rule
                o1_choice = weekend_groups[week_num]['o1']
                if o1_choice not in a1:
                    violations.append(f"Day {d_num}: Weekend Continuity Broken for Oncall 1 ({o1_choice} on leave/no-oncall)")
                    row["Oncall 1"] = a1[0]
                else:
                    row["Oncall 1"] = o1_choice
                
                o2_choice = weekend_groups[week_num]['o2']
                if o2_choice not in a2:
                    violations.append(f"Day {d_num}: Weekend Continuity Broken for Oncall 2 ({o2_choice} on leave/no-oncall)")
                    row["Oncall 2"] = a2[0]
                else:
                    row["Oncall 2"] = o2_choice
            else:
                row["Oncall 1"], row["Oncall 2"] = random.choice(a1), random.choice(a2)

        # --- Oncall 3 (Weekend/PH) ---
        if is_weekend or is_ph:
            a3 = get_avail(pool_3rd)
            if a3: row["Oncall 3"] = random.choice(a3)
            else: violations.append(f"Day {d_num}: No staff available for Oncall 3 (Required for Weekend/PH)")

        # --- ELOT ---
        if d_num in elot_days:
            ae = get_avail(pool_elot)
            if is_sat:
                if ae: row["ELOT 1"] = random.choice(ae)
                else: violations.append(f"Day {d_num}: Saturday ELOT 1 slot empty")
            else:
                if len(ae) >= 2:
                    sel = random.sample(ae, 2)
                    row["ELOT 1"], row["ELOT 2"] = sel[0], sel[1]
                else: violations.append(f"Day {d_num}: Not enough staff for ELOT 1 & 2 (Needed 2, found {len(ae)})")

        # --- Minor OT ---
        if d_num in minor_ot_days:
            am = get_avail(pool_minor)
            if len(am) >= 2:
                sel = random.sample(am, 2)
                row["Minor OT 1"], row["Minor OT 2"] = sel[0], sel[1]
            else: violations.append(f"Day {d_num}: Not enough staff for Minor OT 1 & 2")

        # --- Wound Clinic ---
        if d_num in wound_days:
            aw = get_avail(pool_wound)
            if aw: row["Wound Clinic"] = random.choice(aw)
            else: violations.append(f"Day {d_num}: Wound Clinic scheduled but no staff available")

        # --- Passive ---
        avail_passive = [s for s in all_staff if s not in absent]
        if avail_passive:
            row["Passive"] = avail_passive[passive_idx % len(avail_passive)]
            passive_idx += 1
        else:
            violations.append(f"Day {d_num}: No staff available for Passive duty")

        roster_output.append(row)

    return pd.DataFrame(roster_output), violations

# --- 3. UI ---
st.set_page_config(page_title="MedRoster 2026", layout="wide")
st.title("🏥 Medical Roster Generator 2026")

MY_SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(MY_SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Select Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    
    if st.button("Generate Roster"):
        df_final, rules_broken = generate_medical_roster(m_idx, 2026, staff, leave, config)
        
        display_df = df_final.drop(columns=["Is_Special"])
        st.dataframe(display_df, use_container_width=True)
        
        # --- VIOLATIONS SECTION ---
        st.subheader("⚠️ Rules Broken / Conflict Log")
        if not rules_broken:
            st.success("Perfect Roster! No rules were broken.")
        else:
            for rule in rules_broken:
                st.warning(rule)

        # --- SUMMARY TABLE ---
        st.subheader("📊 Duty & Fairness Summary")
        all_names = staff['Staff Name'].dropna().unique()
        summary_data = []
        for name in all_names:
            o1 = (df_final["Oncall 1"] == name).sum()
            o2 = (df_final["Oncall 2"] == name).sum()
            o3 = (df_final["Oncall 3"] == name).sum()
            special_days_df = df_final[df_final["Is_Special"] == True]
            weekend_ph_count = ((special_days_df["Oncall 1"] == name).sum() + (special_days_df["Oncall 2"] == name).sum() + (special_days_df["Oncall 3"] == name).sum())
            summary_data.append({
                "Name": name, "Oncall 1": o1, "Oncall 2": o2, "Oncall 3": o3,
                "Total Oncall": o1 + o2 + o3, "Total Weekend/PH Oncall": weekend_ph_count,
                "Passive": (df_final["Passive"] == name).sum(), "ELOT 1": (df_final["ELOT 1"] == name).sum(),
                "ELOT 2": (df_final["ELOT 2"] == name).sum(), "Minor OT 1": (df_final["Minor OT 1"] == name).sum(),
                "Minor OT 2": (df_final["Minor OT 2"] == name).sum(), "Wound Clinic": (df_final["Wound Clinic"] == name).sum()
            })
        st.table(pd.DataFrame(summary_data))
