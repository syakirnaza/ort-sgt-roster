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
        st.error(f"Error loading data: {e}")
        return None, None, None

# --- 2. THE IMPROVED SIMULATION ENGINE ---
def run_simulation(month_idx, year, staff_df, leave_df, config_df):
    num_days = calendar.monthrange(year, month_idx)[1]
    days = [date(year, month_idx, d) for d in range(1, num_days + 1)]
    
    target_month = calendar.month_name[month_idx]
    m_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month]
    
    def get_conf(col_idx):
        if m_config.empty: return []
        val = str(m_config.iloc[0, col_idx])
        return [int(x.strip()) for x in val.split(',') if x.strip().isdigit()] if val != 'nan' else []

    ph_days, elot_days, minor_days, wound_days = get_conf(1), get_conf(2), get_conf(3), get_conf(4)
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    # Mapping pools directly to column names to avoid index errors
    pools = {
        "o1": staff_df[staff_df.columns[staff_df.columns.str.contains('1st call', case=False)]].iloc[:,0].dropna().tolist(),
        "o2": staff_df[staff_df.columns[staff_df.columns.str.contains('2nd call', case=False)]].iloc[:,0].dropna().tolist(),
        "o3": staff_df[staff_df.columns[staff_df.columns.str.contains('3rd call', case=False)]].iloc[:,0].dropna().tolist(),
        "elot": staff_df[staff_df.columns[staff_df.columns.str.contains('ELOT 1', case=False)]].iloc[:,0].dropna().tolist(),
        "minor": staff_df[staff_df.columns[staff_df.columns.str.contains('Minor OT 1', case=False)]].iloc[:,0].dropna().tolist(),
        "wound": staff_df[staff_df.columns[staff_df.columns.str.contains('Wound Clinic', case=False)]].iloc[:,0].dropna().tolist()
    }

    roster, total_penalties = [], 0
    passive_idx = random.randint(0, 100)
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

        occupied_today = set()

        def get_avail(pool, duty_type):
            pool = [s for s in pool if s not in absent]
            if duty_type in ["oncall", "passive", "elot"]:
                pool = [s for s in pool if s not in restricted]
            pool = [s for s in pool if s not in occupied_today]
            if duty_type == "elot" and day.weekday() != 5: # Post-call rule for ELOT
                pool = [s for s in pool if s not in prev_day_oncalls]
            return pool

        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        # --- WEEKEND GROUP LOGIC ---
        if is_sun and len(weekend_group) == 3:
            # Re-use Saturday group but rotate roles
            random.shuffle(weekend_group)
            # Ensure O1 today is not O1 yesterday
            if weekend_group[0] == roster[-1]["Oncall 1"]:
                weekend_group[0], weekend_group[1] = weekend_group[1], weekend_group[0]
            
            for i, call_key in enumerate(["Oncall 1", "Oncall 2", "Oncall 3"]):
                p = weekend_group[i]
                if p not in absent and p not in restricted:
                    row[call_key] = p
                    occupied_today.add(p)
                else: total_penalties += 2000 # Leave broke group continuity
        else:
            if is_sat: weekend_group = []
            # Standard Assignment for Weekdays/Saturday/PH
            for call_key, pool_key in [("Oncall 1", "o1"), ("Oncall 2", "o2"), ("Oncall 3", "o3")]:
                if call_key == "Oncall 3" and not is_spec: continue
                a = get_avail(pools[pool_key], "oncall")
                if a:
                    pick = random.choice(a)
                    row[call_key] = pick
                    occupied_today.add(pick)
                    if is_sat: weekend_group.append(pick)
                else: total_penalties += 5000

        # --- ELOT, MINOR, WOUND ---
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if is_sat and ae: row["ELOT 1"] = random.choice(ae)
            elif len(ae) >= 2: row["ELOT 1"], row["ELOT 2"] = random.sample(ae, 2)

        if d_num in minor_days:
            am = get_avail(pools["minor"], "minor")
            if len(am) >= 2: row["Minor OT 1"], row["Minor OT 2"] = random.sample(am, 2)

        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound")
            if aw: row["Wound Clinic"] = random.choice(aw)

        # --- PASSIVE ---
        ap = get_avail(all_staff, "passive")
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1
            occupied_today.add(row["Passive"])

        prev_day_oncalls = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]}
        roster.append(row)

    # --- SCORING FOR EQUALITY ---
    df = pd.DataFrame(roster)
    all_oncalls = pd.concat([df["Oncall 1"], df["Oncall 2"], df["Oncall 3"]]).value_counts().reindex(all_staff, fill_value=0)
    spec_oncalls = pd.concat([df[df["Is_Spec"]==True][c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]]).value_counts().reindex(all_staff, fill_value=0)
    
    score = total_penalties + (np.std(all_oncalls) * 150) + (np.std(spec_oncalls) * 300)
    return df, score

# --- 3. OPTIMIZER WRAPPER ---
def optimize_roster(m_idx, year, staff, leave, config, iterations):
    best_df, best_score = None, float('inf')
    bar = st.progress(0)
    for i in range(1, iterations + 1):
        df, score = run_simulation(m_idx, year, staff, leave, config)
        if score < best_score:
            best_score, best_df = score, df
        if i % 500 == 0: bar.progress(i/iterations)
    return best_df

# --- 4. UI ---
st.set_page_config(page_title="Safe Roster Optimizer", layout="wide")
st.title("🏥 Medical Roster: Group Continuity & Absolute Safety")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Optimized Roster"):
        final_df = optimize_roster(m_idx, 2026, staff, leave, config, sims)
        st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)
        
        # Summary Audit
        summary = []
        for name in staff['Staff Name'].dropna().unique():
            o_tot = (final_df["Oncall 1"]==name).sum() + (final_df["Oncall 2"]==name).sum() + (final_df["Oncall 3"]==name).sum()
            w_tot = (final_df[final_df["Is_Spec"]==True][["Oncall 1","Oncall 2","Oncall 3"]]==name).sum().sum()
            summary.append({"Name": name, "Total Oncall": o_tot, "Weekend/PH": w_tot})
        st.table(pd.DataFrame(summary))
