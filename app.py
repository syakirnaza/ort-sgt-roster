import streamlit as st
import pandas as pd
import calendar
import random
import numpy as np
from datetime import date
from multiprocessing import Pool, cpu_count

# --- 1. DATA LOADING (CLEANED) ---
@st.cache_data(ttl=60)
def load_all_data(sheet_id):
    def get_url(name): return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={name}"
    try:
        staff_df = pd.read_csv(get_url("StaffList"))
        leave_df = pd.read_csv(get_url("LeaveRequest"))
        config_df = pd.read_csv(get_url("Configuration"))
        
        # Trim headers and string data
        for df in [staff_df, leave_df, config_df]:
            df.columns = df.columns.astype(str).str.strip()
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

        def get_avail(pool, duty_type):
            res = [s for s in pool if s not in absent and s not in daily_occupied]
            if duty_type == "elot" and not is_sat:
                res = [s for s in res if s not in post_call_shield]
            return res

        # ONCALL LOGIC (With Weekend Team Continuity)
        if is_sun and len(weekend_team) == 3:
            sun_pool = [s for s in weekend_team if s not in absent]
            if len(sun_pool) < 3:
                total_penalties += 2000
                sun_pool = get_avail(pools["o1"], "oncall")[:3]
            
            random.shuffle(sun_pool)
            if len(sun_pool) > 1 and sun_pool[0] == prev_sat_o1:
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

        # PASSIVE (Uses Column E specifically)
        ap = get_avail(pools["passive"], "passive")
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1
            daily_occupied.add(row["Passive"])

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    # Scoring
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
    all_staff = staff_df['Staff Name'].dropna().tolist()
    
    # Pool Mapping
    pools = {
        "o1": staff_df['1st call'].dropna().tolist(),
        "o2": staff_df['2nd call'].dropna().tolist(),
        "o3": staff_df['3rd call'].dropna().tolist(),
        "passive": staff_df.iloc[:, 4].dropna().tolist() # Column E is now Passive Pool
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
        with st.spinner(f"Simulating {sims} variations..."):
            final_df = optimize_parallel(m_idx, 2026, staff, leave, config, sims)
            st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)
            
            # Audit
            st.subheader("📊 Workload Audit")
            audit = []
            for n in staff['Staff Name'].dropna().unique():
                o_tot = (final_df[["Oncall 1", "Oncall 2", "Oncall 3"]] == n).sum().sum()
                audit.append({"Staff Name": n, "Total Oncalls": o_tot})
            st.table(pd.DataFrame(audit))
