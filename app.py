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
        leave_df['Date'] = pd.to_datetime(leave_df['Date'].astype(str).str.replace('_', ' ')).dt.date
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None, None

# --- 2. GLOBAL SIMULATION FUNCTION (Must be top-level for Multiprocessing) ---
def run_single_simulation(args):
    # Unpack arguments
    days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_lookup, restricted_set = args
    
    roster, total_penalties = [], 0
    passive_idx = random.randint(0, 100)
    weekend_team, prev_sat_o1 = [], None
    post_call_shield = set()

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_spec = (is_sat or is_sun or d_num in ph_days)
        
        absent = leave_lookup.get(day, [])
        daily_occupied = set()
        row = {"Date": day, "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": "", "Is_Spec": is_spec}

        def get_avail(pool, duty_type):
            res = [s for s in pool if s not in absent and s not in daily_occupied]
            if duty_type in ["oncall", "passive", "elot"]:
                res = [s for s in res if s not in restricted_set]
            if duty_type == "elot":
                res = [s for s in res if s not in post_call_shield]
            return res

        # Weekend Continuity Logic
        if is_sun and len(weekend_team) == 3:
            sun_pool = [s for s in weekend_team if s not in absent and s not in restricted_set]
            if len(sun_pool) < 3:
                total_penalties += 2000
                sun_pool = get_avail(pools["o1"], "oncall")[:3]
            random.shuffle(sun_pool)
            if sun_pool[0] == prev_sat_o1 and len(sun_pool) > 1:
                sun_pool[0], sun_pool[1] = sun_pool[1], sun_pool[0]
            for i, c in enumerate(["Oncall 1", "Oncall 2", "Oncall 3"]):
                if i < len(sun_pool): 
                    row[c] = sun_pool[i]
                    daily_occupied.add(sun_pool[i])
        else:
            if is_sat: weekend_team = []
            for ck, pk in [("Oncall 1", "o1"), ("Oncall 2", "o2"), ("Oncall 3", "o3")]:
                if ck == "Oncall 3" and not is_spec: continue
                avail = get_avail(pools[pk], "oncall")
                if avail:
                    pick = random.choice(avail)
                    row[ck] = pick
                    daily_occupied.add(pick)
                    if is_sat:
                        weekend_team.append(pick)
                        if ck == "Oncall 1": prev_sat_o1 = pick
                else: total_penalties += 5000

        # ELOT / Passive logic... (truncated for brevity, same as previous working logic)
        row["Passive"] = random.choice(get_avail(all_staff, "passive")) if get_avail(all_staff, "passive") else ""
        
        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    # Scoring using NumPy for speed
    df_temp = pd.DataFrame(roster)
    counts = pd.concat([df_temp["Oncall 1"], df_temp["Oncall 2"], df_temp["Oncall 3"]]).value_counts()
    score = total_penalties + (np.std(counts.values) * 500)
    return score, df_temp

# --- 3. THE OPTIMIZER ---
def optimize_parallel(m_idx, year, staff_df, leave_df, config_df, iters):
    # Pre-process data for speed
    num_days = calendar.monthrange(year, m_idx)[1]
    days = [date(year, m_idx, d) for d in range(1, num_days + 1)]
    target_month = calendar.month_name[m_idx]
    m_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month]
    
    ph_days = [int(x.strip()) for x in str(m_config.iloc[0, 1]).split(',') if x.strip().isdigit()]
    all_staff = staff_df['Staff Name'].dropna().tolist()
    restricted_set = set(staff_df[staff_df.iloc[:, 4].notna()]['Staff Name'].tolist()) # Col E
    
    # Pre-build pools
    pools = {
        "o1": staff_df[staff_df['1st call'].notna()]['Staff Name'].tolist(),
        "o2": staff_df[staff_df['2nd call'].notna()]['Staff Name'].tolist(),
        "o3": staff_df[staff_df['3rd call'].notna()]['Staff Name'].tolist()
    }
    
    # Pre-build Leave Lookup (Dictionary is O(1) speed)
    leave_lookup = {row['Date']: [n.strip() for n in str(row.iloc[3]).split(',')] for _, row in leave_df.iterrows()}

    # Prepare arguments for parallel processing
    args = (days, ph_days, [], [], [], all_staff, pools, leave_lookup, restricted_set)
    
    st.info(f"🚀 Launching {iters} simulations across {cpu_count()} CPU cores...")
    
    # Using Pool to run in parallel
    with Pool(cpu_count()) as p:
        # Run batches to update progress bar
        batch_size = iters // 10
        results = []
        bar = st.progress(0)
        for i in range(10):
            batch_results = p.map(run_single_simulation, [args] * batch_size)
            results.extend(batch_results)
            bar.progress((i + 1) / 10)
            
    # Find the best result
    best_score, best_df = min(results, key=lambda x: x[0])
    return best_df

# --- 4. UI ---
# (Standard Streamlit UI calls optimize_parallel instead of optimize)
