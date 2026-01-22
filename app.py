import streamlit as st
import pandas as pd
import calendar
import random
import numpy as np
from datetime import date
from multiprocessing import Pool, cpu_count

# --- 1. DATA LOADING (STABLE) ---
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

# --- 2. THE SIMULATION CORE (OPTIMIZED FOR MULTIPROCESSING) ---
def run_single_simulation(args):
    # Unpack pre-processed arguments
    days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_lookup, restricted_set = args
    
    roster = []
    total_penalties = 0
    weekend_team, prev_sat_o1 = [], None
    post_call_shield = set()
    passive_idx = random.randint(0, 100)

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
            if duty_type in ["oncall", "passive", "elot"]:
                res = [s for s in res if s not in restricted_set]
            if duty_type == "elot" and not is_sat: # Rest rule
                res = [s for s in res if s not in post_call_shield]
            return res

        # ONCALL LOGIC
        if is_sun and len(weekend_team) == 3:
            sun_pool = [s for s in weekend_team if s not in absent and s not in restricted_set]
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

        # OTHER DUTIES
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if is_sat and ae: row["ELOT 1"] = random.choice(ae)
            elif len(ae) >= 2:
                ps = random.sample(ae, 2)
                row["ELOT 1"], row["ELOT 2"] = ps[0], ps[1]
                daily_occupied.update(ps)

        ap = get_avail(all_staff, "passive")
        if ap: row["Passive"] = ap[passive_idx % len(ap)]

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    # VECTORIZED SCORING
    df_temp = pd.DataFrame(roster)
    counts = pd.concat([df_temp["Oncall 1"], df_temp["Oncall 2"], df_temp["Oncall 3"]]).value_counts()
    # High weight on StdDev to force equality
    score = total_penalties + (np.std(counts.values) * 500) 
    return score, df_temp

# --- 3. THE PARALLEL OPTIMIZER ---
def optimize_parallel(m_idx, year, staff_df, leave_df, config_df, iters):
    num_days = calendar.monthrange(year, m_idx)[1]
    days = [date(year, m_idx, d) for d in range(1, num_days + 1)]
    target_month = calendar.month_name[m_idx]
    m_config = config_df[config_df.iloc[:, 0].astype(str).str.strip() == target_month]
    
    # Pre-parse configuration
    def get_c(idx): return [int(x.strip()) for x in str(m_config.iloc[0, idx]).split(',') if x.strip().isdigit()]
    ph_days, elot_days, minor_days, wound_days = get_c(1), get_c(2), get_c(3), get_c(4)
    
    all_staff = staff_df['Staff Name'].dropna().tolist()
    # Column E (5th column) restricted staff
    restricted_set = set(staff_df[staff_df.iloc[:, 4].notna()]['Staff Name'].tolist())
    
    def get_p(col_name): return staff_df[staff_df[col_name].notna()]['Staff Name'].tolist()
    pools = {"o1": get_p('1st call'), "o2": get_p('2nd call'), "o3": get_p('3rd call'), "elot": get_p('ELOT 1')}
    
    leave_lookup = {row['Date']: [n.strip() for n in str(row.iloc[3]).split(',')] for _, row in leave_df.iterrows()}

    args = (days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_lookup, restricted_set)
    
    # Execute Parallel Processing
    with Pool(cpu_count()) as p:
        # Use imap_unordered for better performance
        results = p.map(run_single_simulation, [args] * iters)
            
    best_score, best_df = min(results, key=lambda x: x[0])
    return best_df

# --- 4. STREAMLIT UI ---
st.set_page_config(page_title="HPC Parallel Optimizer", layout="wide")
st.title("🏥 Medical Roster: High-Performance Equality Engine")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Final Optimized Roster"):
        with st.spinner(f"Running {sims} simulations in parallel..."):
            final_df = optimize_parallel(m_idx, 2026, staff, leave, config, sims)
            st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)
            
            # Audit Table
            st.subheader("📊 Equality Audit")
            audit_data = []
            for name in staff['Staff Name'].dropna().unique():
                o_tot = (final_df[["Oncall 1", "Oncall 2", "Oncall 3"]] == name).sum().sum()
                w_tot = (final_df[final_df["Is_Spec"]][["Oncall 1", "Oncall 2", "Oncall 3"]] == name).sum().sum()
                audit_data.append({"Staff Name": name, "Total Oncalls": o_tot, "Weekend/PH": w_tot})
            st.table(pd.DataFrame(audit_data))
