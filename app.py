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
            df[:] = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        leave_df['Date'] = pd.to_datetime(leave_df['Date'].astype(str).str.replace('_', ' ')).dt.date
        return staff_df, leave_df.dropna(subset=['Date']), config_df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return None, None, None

# --- 2. THE SIMULATION CORE ---
def run_single_simulation(args):
    days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_lookup = args
    roster, total_penalties = [], 0
    weekend_team, prev_sat_o1 = [], None
    post_call_shield = set() 
    passive_idx = random.randint(0, 100)

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_ph = d_num in ph_days
        is_spec = (is_sat or is_sun or is_ph)
        
        absent = leave_lookup.get(day, [])
        daily_occupied = set()
        
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool, duty_type="general"):
            res = [s for s in pool if s not in absent and s not in daily_occupied]
            if duty_type == "oncall":
                res = [s for s in res if s not in post_call_shield]
            return res

        # ONCALL LOGIC
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
                    if is_sat: weekend_team.append(pick)
                    if is_sat and ck == "Oncall 1": prev_sat_o1 = pick
                else: total_penalties += 5000

        # ELOT, MINOR, WOUND
        if d_num in elot_days:
            ae = get_avail(pools["elot"])
            if len(ae) >= 2: row["ELOT 1"], row["ELOT 2"] = random.sample(ae, 2)
            elif ae: row["ELOT 1"] = ae[0]

        if d_num in minor_days:
            am = get_avail(pools["minor"])
            if len(am) >= 2: row["Minor OT 1"], row["Minor OT 2"] = random.sample(am, 2)

        if d_num in wound_days:
            aw = get_avail(pools["wound"])
            if aw: row["Wound Clinic"] = random.choice(aw)

        # PASSIVE
        ap = get_avail(pools["passive"])
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    df_res = pd.DataFrame(roster)
    counts = pd.concat([df_res["Oncall 1"], df_res["Oncall 2"], df_res["Oncall 3"]]).value_counts()
    score = total_penalties + (np.std(counts.values) * 500) if not counts.empty else 10**6
    return score, df_res

# --- 3. UI & OPTIMIZER ---
st.set_page_config(page_title="HPC Optimizer", layout="wide")
st.title("🏥 Medical Roster: High-Performance Equality Engine")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Mathematically Fair Roster"):
        target_month = calendar.month_name[m_idx]
        m_cfg = config[config.iloc[:, 0].astype(str) == target_month]
        def get_cfg(i): return [int(x.strip()) for x in str(m_cfg.iloc[0, i]).split(',') if x.strip().isdigit()] if not m_cfg.empty else []
        
        ph, elot, minor, wound = get_cfg(1), get_cfg(2), get_cfg(3), get_cfg(4)
        def get_names(col): return staff[staff[col].astype(str).str.lower() == 'yes']['Staff Name'].tolist()

        pools = {"o1": get_names('1st call'), "o2": get_names('2nd call'), "o3": get_names('3rd call'),
                 "passive": get_names(staff.columns[4]), "elot": get_names('ELOT 1'),
                 "minor": get_names('Minor OT 1'), "wound": get_names('Wound Clinic')}
        
        days = [date(2026, m_idx, d) for d in range(1, calendar.monthrange(2026, m_idx)[1] + 1)]
        leave_lkp = {r['Date']: [n.strip() for n in str(r.iloc[3]).split(',')] for _, r in leave.iterrows()}
        args = (days, ph, elot, minor, wound, staff['Staff Name'].tolist(), pools, leave_lkp)

        best_score, best_df = float('inf'), None
        prog_bar = st.progress(0)
        status = st.empty()

        with Pool(cpu_count()) as p:
            batch_size = sims // 20
            for i in range(20):
                batch = p.map(run_single_simulation, [args] * batch_size)
                m_score, m_df = min(batch, key=lambda x: x[0])
                if m_score < best_score:
                    best_score, best_df = m_score, m_df
                percent = (i + 1) * 5
                prog_bar.progress(percent)
                status.write(f"**Optimization Progress: {percent}%**")

        st.success("Roster Generation Complete!")
        
        # Fairness Meter
        st.subheader("⚖️ Fairness Meter")
        fair_val = max(0, 100 - (best_score / 200))
        st.progress(min(100.0, fair_val) / 100)
        st.write(f"Workload Balance Score: **{fair_val:.1f}%**")

        # EDITABLE ROSTER
        st.subheader("✏️ Roster Editor")
        st.info("You can click any cell to manually swap names. The summary below will update automatically.")
        # Note: We keep Is_Spec for the summary calculations
        edited_df = st.data_editor(best_df, use_container_width=True, hide_index=True)

        # --- FINAL SUMMARY AUDIT ---
        st.divider()
        st.subheader("📊 Comprehensive Duty Audit")
        
        summary_list = []
        for name in staff['Staff Name'].dropna().unique():
            # Filter for this person
            o1 = (edited_df["Oncall 1"] == name).sum()
            o2 = (edited_df["Oncall 2"] == name).sum()
            o3 = (edited_df["Oncall 3"] == name).sum()
            
            # Weekend/PH logic
            wknd_ph = (edited_df[edited_df["Is_Spec"] == True][["Oncall 1", "Oncall 2", "Oncall 3"]] == name).sum().sum()
            
            summary_list.append({
                "Staff Name": name,
                "Oncall 1": o1,
                "Oncall 2": o2,
                "Oncall 3": o3,
                "Total Oncall": o1 + o2 + o3,
                "Weekend/PH": wknd_ph,
                "Total ELOT": (edited_df[["ELOT 1", "ELOT 2"]] == name).sum().sum(),
                "Total Minor OT": (edited_df[["Minor OT 1", "Minor OT 2"]] == name).sum().sum()
            })
        
        st.table(pd.DataFrame(summary_list))
