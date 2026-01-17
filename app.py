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
        
        # Date parsing
        leave_df['Date'] = pd.to_datetime(leave_df['Date'].astype(str).str.replace('_', ' ')).dt.date
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None

# --- 2. THE SIMULATION ENGINE ---
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
    
    def get_pool(col): return staff_df[staff_df[col].notna()]['Staff Name'].tolist() if col in staff_df.columns else all_staff

    pools = {"o1": get_pool('1st call'), "o2": get_pool('2nd call'), "o3": get_pool('3rd call'),
             "elot": get_pool('ELOT 1'), "minor": get_pool('Minor OT 1'), "wound": get_pool('Wound Clinic')}

    roster, total_penalties = [], 0
    passive_idx = random.randint(0, 50)
    sat_assignments = {"o1": None, "o2": None, "o3": None}

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

        def get_avail(pool, duty_type):
            pool = [s for s in pool if s not in absent]
            # Strict Rule: Col E excluded from Oncalls, Passive, and ELOT
            if duty_type in ["oncall", "passive", "elot"]:
                pool = [s for s in pool if s not in restricted]
            return pool

        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        # --- Oncall 1 (Hard Weekend Swap) ---
        a1 = get_avail(pools["o1"], "oncall")
        if a1:
            eligible_o1 = [s for s in a1 if s != sat_assignments["o1"]] if is_sun else a1
            if not eligible_o1:
                row["Oncall 1"] = random.choice(a1)
                total_penalties += 500 # Penalty for repeating O1 on weekend
            else:
                row["Oncall 1"] = random.choice(eligible_o1)
            if is_sat: sat_assignments["o1"] = row["Oncall 1"]
        else: total_penalties += 1000

        # --- Oncall 2 & 3 (Soft Weekend Swap) ---
        a2 = get_avail(pools["o2"], "oncall")
        if a2:
            eligible_o2 = [s for s in a2 if s != sat_assignments["o2"]] if is_sun else a2
            row["Oncall 2"] = random.choice(eligible_o2) if eligible_o2 else random.choice(a2)
            if is_sat: sat_assignments["o2"] = row["Oncall 2"]
        
        if is_spec:
            a3 = get_avail(pools["o3"], "oncall")
            if a3:
                eligible_o3 = [s for s in a3 if s != sat_assignments["o3"]] if is_sun else a3
                row["Oncall 3"] = random.choice(eligible_o3) if eligible_o3 else random.choice(a3)
                if is_sat: sat_assignments["o3"] = row["Oncall 3"]

        # --- ELOT, Minor OT, Wound (Strict Col E for ELOT only) ---
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if is_sat: 
                if ae: row["ELOT 1"] = random.choice(ae)
            elif len(ae) >= 2: row["ELOT 1"], row["ELOT 2"] = random.sample(ae, 2)

        if d_num in minor_days:
            am = get_avail(pools["minor"], "minor_ot") # Minor OT can take Col E
            if len(am) >= 2: row["Minor OT 1"], row["Minor OT 2"] = random.sample(am, 2)

        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound") # Wound can take Col E
            if aw: row["Wound Clinic"] = random.choice(aw)

        # --- Passive (Strict Col E exclusion) ---
        ap = get_avail(all_staff, "passive")
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1

        roster.append(row)

    # SCORING
    df = pd.DataFrame(roster)
    spec_df = df[df["Is_Spec"] == True]
    counts = pd.concat([spec_df["Oncall 1"], spec_df["Oncall 2"], spec_df["Oncall 3"]]).value_counts()
    std_dev = np.std(counts) if not counts.empty else 0
    total_score = total_penalties + (std_dev * 50)
    
    return df, total_score

# --- 3. THE OPTIMIZER ---
def optimize_roster(m_idx, year, staff, leave, config, iterations):
    best_df, best_score = None, float('inf')
    bar = st.progress(0)
    status = st.empty()
    for i in range(1, iterations + 1):
        df, score = run_simulation(m_idx, year, staff, leave, config)
        if score < best_score:
            best_score = score
            best_df = df
        if best_score == 0: break # Early Exit on Perfect Roster
        if i % 500 == 0:
            bar.progress(i/iterations)
            status.info(f"Searching... {i}/{iterations} iterations. Best Inequality Score: {best_score:.2f}")
    return best_df

# --- 4. UI ---
st.set_page_config(page_title="HPC Medical Roster", layout="wide")
st.title("🏥 AI-Optimized Medical Roster 2026")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Optimization Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Optimized Roster"):
        final_df = optimize_roster(m_idx, 2026, staff, leave, config, sims)
        st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)

        st.subheader("📊 Duty & Fairness Summary")
        summary = []
        for name in staff['Staff Name'].dropna().unique():
            o1, o2, o3 = (final_df["Oncall 1"]==name).sum(), (final_df["Oncall 2"]==name).sum(), (final_df["Oncall 3"]==name).sum()
            spec = final_df[final_df["Is_Spec"] == True]
            w_count = (spec["Oncall 1"]==name).sum() + (spec["Oncall 2"]==name).sum() + (spec["Oncall 3"]==name).sum()
            summary.append({
                "Name": name, "Oncall 1": o1, "Oncall 2": o2, "Oncall 3": o3,
                "Total Oncall": o1+o2+o3, "Total Weekend/PH": w_count,
                "Passive": (final_df["Passive"]==name).sum(), "ELOT 1": (final_df["ELOT 1"]==name).sum(),
                "ELOT 2": (final_df["ELOT 2"]==name).sum(), "Minor OT 1": (final_df["Minor OT 1"]==name).sum(),
                "Minor OT 2": (final_df["Minor OT 2"]==name).sum(), "Wound Clinic": (final_df["Wound Clinic"]==name).sum()
            })
        st.table(pd.DataFrame(summary))
