import streamlit as st
import pandas as pd
import calendar
import random
import numpy as np
from datetime import date

# --- 1. DATA LOADING ---
@st.cache_data(ttl=60)
def load_all_data(sheet_id):
    def get_url(name): return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={name}"
    try:
        staff_df = pd.read_csv(get_url("StaffList"))
        leave_df = pd.read_csv(get_url("LeaveRequest"))
        config_df = pd.read_csv(get_url("Configuration"))
        for df in [staff_df, leave_df, config_df]:
            df.columns = df.columns.astype(str).str.strip()
        leave_df['Date'] = pd.to_datetime(leave_df['Date'].astype(str).str.replace('_', ' ')).dt.date
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None, None

# --- 2. THE IMPROVED SIMULATION ENGINE ---
def run_simulation(month_idx, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month_idx)[1]
    days = [date(year, month_idx, d) for d in range(1, num_days + 1)]
    
    target_month = calendar.month_name[month_idx]
    m_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month]
    
    def get_conf(col):
        if m_config.empty: return []
        val = str(m_config.iloc[0, col])
        return [int(x.strip()) for x in val.split(',') if x.strip().isdigit()] if val != 'nan' else []

    ph_days, elot_days, minor_days, wound_days = get_conf(1), get_conf(2), get_conf(3), get_conf(4)
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    def get_pool(col): 
        return staff_df[staff_df[col].notna()]['Staff Name'].tolist() if col in staff_df.columns else all_staff

    roster, total_penalties = [], 0
    passive_idx = random.randint(0, 100)
    
    # Tracking for Continuity
    weekend_group = [] 
    prev_day_oncalls = set()

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_ph = d_num in ph_days
        is_spec = (is_sat or is_sun or is_ph)
        
        leave_row = leave_df[leave_df['Date'] == day]
        absent, restricted = [], []
        if not leave_row.empty:
            absent = [n.strip() for n in str(leave_row.iloc[0, 3]).split(',')] if str(leave_row.iloc[0, 3]) != 'nan' else []
            restricted = [n.strip() for n in str(leave_row.iloc[0, 4]).split(',')] if str(leave_row.iloc[0, 4]) != 'nan' else []

        # RESET OR MAINTAIN WEEKEND GROUP
        if is_sat: weekend_group = [] # Start fresh group for the weekend

        # OCCUPIED tracker for CURRENT DAY (Prevents double-booking)
        occupied_today = set()

        def get_avail(pool, duty_type):
            # 1. Basics: No Leave, No Restriction (if applicable)
            pool = [s for s in pool if s not in absent]
            if duty_type in ["oncall", "passive", "elot"]:
                pool = [s for s in pool if s not in restricted]
            
            # 2. Safety: Cannot be picked if already doing another Oncall today
            pool = [s for s in pool if s not in occupied_today]
            
            # 3. Post-Call Rule: Cannot do ELOT if did Oncall yesterday
            if duty_type == "elot":
                pool = [s for s in pool if s not in prev_day_oncalls]
            return pool

        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        # --- ONCALL SELECTION ---
        calls = ["Oncall 1", "Oncall 2", "Oncall 3"]
        
        if is_sun and len(weekend_group) == 3:
            # SUNDAY LOGIC: Rotate the SATURDAY GROUP
            random.shuffle(weekend_group)
            # Ensure Sunday O1 != Saturday O1
            if weekend_group[0] == roster[-1]["Oncall 1"]:
                weekend_group[0], weekend_group[1] = weekend_group[1], weekend_group[0]
            
            for i, call in enumerate(calls):
                person = weekend_group[i]
                if person not in absent and person not in restricted:
                    row[call] = person
                    occupied_today.add(person)
                else: total_penalties += 1000 # Leave broke the group continuity
        else:
            # SATURDAY/WEEKDAY/PH LOGIC: Fresh selection
            for call in calls:
                if call == "Oncall 3" and not is_spec: continue
                
                pool_key = "o1" if call == "Oncall 1" else ("o2" if call == "Oncall 2" else "o3")
                a = get_avail(get_pool(staff_df.columns[staff_df.columns.str.contains(pool_key, case=False)][0]), "oncall")
                
                if a:
                    pick = random.choice(a)
                    row[call] = pick
                    occupied_today.add(pick)
                    if is_sat: weekend_group.append(pick)
                else: total_penalties += 5000

        # --- OTHER DUTIES (Respecting occupied_today) ---
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if is_sat and ae: row["ELOT 1"] = random.choice(ae)
            elif len(ae) >= 2: row["ELOT 1"], row["ELOT 2"] = random.sample(ae, 2)

        if d_num in minor_days:
            am = [s for s in pools["minor"] if s not in absent and s not in occupied_today]
            if len(am) >= 2: row["Minor OT 1"], row["Minor OT 2"] = random.sample(am, 2)

        if d_num in wound_days:
            aw = [s for s in pools["wound"] if s not in absent and s not in occupied_today]
            if aw: row["Wound Clinic"] = random.choice(aw)

        # Passive
        ap = get_avail(all_staff, "passive")
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1
            occupied_today.add(row["Passive"])

        prev_day_oncalls = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]}
        roster.append(row)

    # --- SCORING ---
    df = pd.DataFrame(roster)
    total_counts = pd.concat([df["Oncall 1"], df["Oncall 2"], df["Oncall 3"]]).value_counts().reindex(all_staff, fill_value=0)
    spec_counts = pd.concat([df[df["Is_Spec"]==True][c] for c in calls]).value_counts().reindex(all_staff, fill_value=0)
    
    score = total_penalties + (np.std(total_counts)*200) + (np.std(spec_counts)*300)
    return df, score

# --- 3. UI ---
st.set_page_config(page_title="Safe Roster Optimizer", layout="wide")
st.title("🏥 Critical Safety Roster Optimizer")
st.info("Rule: Weekend Group remains the same for Sat/Sun, but roles rotate. Double-booking is strictly forbidden.")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_idx = list(calendar.month_name).index(st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m]))
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Safe Roster"):
        final_df, _ = run_simulation(m_idx, 2026, staff, leave, config) # Running optimizer call
        st.dataframe(final_df.drop(columns=["Is_Spec"]))
