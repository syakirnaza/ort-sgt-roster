import streamlit as st
import pandas as pd
import calendar
import random
import numpy as np
from datetime import date
from multiprocessing import Pool, cpu_count

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
            # Remove whitespace but keep original case for Yes/No matching
            df[:] = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            
        leave_df['Date'] = pd.to_datetime(leave_df['Date'].astype(str).str.replace('_', ' ')).dt.date
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return None, None, None

# --- 2. THE SIMULATION CORE ---
def run_single_simulation(args):
    days, ph_days, elot_days, all_staff, pools, leave_lookup = args
    roster, total_penalties = [], 0
    weekend_team, prev_sat_o1 = [], None
    post_call_shield = set()
    passive_idx = random.randint(0, 1000)

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_spec = (is_sat or is_sun or d_num in ph_days)
        
        absent = leave_lookup.get(day, [])
        daily_occupied = set()
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool):
            return [s for s in pool if s not in absent and s not in daily_occupied]

        # ONCALL 1 & 2
        for c_name, p_key in [("Oncall 1", "o1"), ("Oncall 2", "o2")]:
            avail = get_avail(pools[p_key])
            if is_sun and c_name == "Oncall 1" and prev_sat_o1 in avail and len(avail) > 1:
                # Rotation: Ensure Sunday O1 is different from Saturday O1
                avail = [s for s in avail if s != prev_sat_o1]
            
            if avail:
                pick = random.choice(avail)
                row[c_name] = pick
                daily_occupied.add(pick)
                if is_sat and c_name == "Oncall 1": prev_sat_o1 = pick
            else: total_penalties += 5000

        # ONCALL 3 (Specials only)
        if is_spec:
            avail3 = get_avail(pools["o3"])
            if avail3:
                pick3 = random.choice(avail3)
                row["Oncall 3"] = pick3
                daily_occupied.add(pick3)

        # PASSIVE (Column E)
        avail_p = get_avail(pools["passive"])
        if avail_p:
            row["Passive"] = avail_p[passive_idx % len(avail_p)]
            passive_idx += 1
            daily_occupied.add(row["Passive"])

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    df_temp = pd.DataFrame(roster)
    counts = pd.concat([df_temp["Oncall 1"], df_temp["Oncall 2"], df_temp["Oncall 3"]]).value_counts()
    score = total_penalties + (np.std(counts.values) * 500) if not counts.empty else 999999
    return score, df_temp

# --- 3. THE OPTIMIZER ---
def optimize_parallel(m_idx, year, staff_df, leave_df, config_df, iters):
    num_days = calendar.monthrange(year, m_idx)[1]
    days = [date(year, m_idx, d) for d in range(1, num_days + 1)]
    target_month = calendar.month_name[m_idx]
    m_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month]
    ph_days = [int(x.strip()) for x in str(m_config.iloc[0, 1]).split(',') if x.strip().isdigit()] if not m_config.empty else []

    # --- CRITICAL FIX: MAP "YES" TO NAMES ---
    def get_names_where_yes(col_name):
        # Look at the column. If it says 'Yes', get the name from 'Staff Name' column.
        return staff_df[staff_df[col_name].astype(str).str.lower() == 'yes']['Staff Name'].tolist()

    all_staff = staff_df['Staff Name'].dropna().tolist()
    pools = {
        "o1": get_names_where_yes('1st call'),
        "o2": get_names_where_yes('2nd call'),
        "o3": get_names_where_yes('3rd call'),
        "passive": get_names_where_yes(staff_df.columns[4]) # Column E
    }
    
    leave_lookup = {row['Date']: [n.strip() for n in str(row.iloc[3]).split(',')] for _, row in leave_df.iterrows()}
    args = (days, ph_days, [], all_staff, pools, leave_lookup)
    
    with Pool(cpu_count()) as p:
        results = p.map(run_single_simulation, [args] * iters)
            
    best_score, best_df = min(results, key=lambda x: x[0])
    return best_df

# --- 4. UI ---
st.set_page_config(page_title="HPC Parallel Optimizer", layout="wide")
st.title("🏥 Medical Roster: Parallel Equality Engine")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Optimized Roster"):
        with st.spinner(f"Filtering {sims} variations for fairness..."):
            final_df = optimize_parallel(m_idx, 2026, staff, leave, config, sims)
            st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)
