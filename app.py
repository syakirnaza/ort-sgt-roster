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
    days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_data = args
    roster, total_penalties = [], 0
    post_call_shield = set() 
    weekend_team = []
    passive_idx = random.randint(0, 100)
    elot_idx = random.randint(0, 100)

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_ph = d_num in ph_days
        is_spec = (is_sat or is_sun or is_ph)
        day_info = leave_data.get(day, {"absent": [], "restricted": []})
        absent, restricted = day_info["absent"], day_info["restricted"]
        
        daily_occupied = set()
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool, duty_type):
            res = []
            for s in pool:
                if s in daily_occupied or s in absent: continue
                if s in restricted and duty_type in ["oncall", "passive", "elot"]: continue
                if duty_type == "oncall" and s in post_call_shield: continue
                res.append(s)
            return res

        # 1. Oncalls (Weekend logic included)
        if is_sun and weekend_team:
            sun_pool = get_avail(weekend_team, "oncall")
            if len(sun_pool) < 3: 
                total_penalties += 1000
                sun_pool += get_avail(pools["o1"], "oncall")
            random.shuffle(sun_pool)
            for i, duty in enumerate(["Oncall 1", "Oncall 2", "Oncall 3"]):
                if i < len(sun_pool):
                    row[duty] = sun_pool[i]
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
                else: total_penalties += 5000

        # 2. Passive & ELOT (Round Robin)
        if not is_spec:
            ap = get_avail(pools["passive"], "passive")
            if ap:
                row["Passive"] = ap[passive_idx % len(ap)]
                passive_idx += 1
                daily_occupied.add(row["Passive"])

        if d_num in elot_days:
            ae1 = get_avail(pools["elot1"], "elot")
            p1 = ae1[elot_idx % len(ae1)] if ae1 else None
            if p1:
                row["ELOT 1"] = p1
                daily_occupied.add(p1)
            
            ae2 = get_avail(pools["elot2"], "elot")
            ae2_rem = [s for s in ae2 if s != p1]
            if ae2_rem:
                p2 = ae2_rem[elot_idx % len(ae2_rem)]
                row["ELOT 2"] = p2
                daily_occupied.add(p2)
            elot_idx += 1

        # 3. Minor OT & Wound
        if d_num in minor_days:
            am1 = get_avail(pools["minor1"], "minor")
            pm1 = random.choice(am1) if am1 else None
            if pm1:
                row["Minor OT 1"] = pm1
                daily_occupied.add(pm1)
            am2 = get_avail(pools["minor2"], "minor")
            am2_rem = [s for s in am2 if s != pm1]
            if am2_rem:
                row["Minor OT 2"] = random.choice(am2_rem)
                daily_occupied.add(row["Minor OT 2"])

        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound")
            if aw: row["Wound Clinic"] = random.choice(aw)

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    df_temp = pd.DataFrame(roster)
    oc_counts = pd.concat([df_temp[c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]]).value_counts()
    elot_counts = pd.concat([df_temp[c] for c in ["ELOT 1", "ELOT 2"]]).value_counts()
    oc_std = np.std(oc_counts.values) if not oc_counts.empty else 100
    elot_std = np.std(elot_counts.values) if not elot_counts.empty else 100
    
    score = total_penalties + (oc_std * 1000) + (elot_std * 500)
    return score, df_temp

# --- 3. UI ---
st.set_page_config(page_title="Roster Generator", layout="wide")
st.title("🏥 Ortho Segamat Monthly Roster")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.slider("Intensity", 1000, 50000, 10000, 1000)

    if st.button("Generate Roster"):
        target_month = calendar.month_name[m_idx]
        m_cfg = config[config.iloc[:, 0].astype(str) == target_month]
        def get_cfg(i): return [int(x.strip()) for x in str(m_cfg.iloc[0, i]).split(',') if x.strip().isdigit()] if not m_cfg.empty else []
        ph, elot, minor, wound = get_cfg(1), get_cfg(2), get_cfg(3), get_cfg(4)
        
        leave_map = {}
        for _, r in leave.iterrows():
            leave_map[r['Date']] = {"absent": [n.strip() for n in str(r.iloc[3]).split(',')], "restricted": [n.strip() for n in str(r.iloc[4]).split(',')]}

        def get_names(sub):
            col = [c for c in staff.columns if sub.lower() in c.lower()]
            return staff[staff[col[0]].astype(str).str.lower() == 'yes']['Staff Name'].tolist() if col else []

        pools = {"o1": get_names('1st call'), "o2": get_names('2nd call'), "o3": get_names('3rd call'),
                 "passive": get_names('Passive'), "elot1": get_names('ELOT 1'), "elot2": get_names('ELOT 2'),
                 "minor1": get_names('Minor 1'), "minor2": get_names('Minor 2'), "wound": get_names('Wound')}
        
        days = [date(2026, m_idx, d) for d in range(1, calendar.monthrange(2026, m_idx)[1] + 1)]
        args = (days, ph, elot, minor, wound, staff['Staff Name'].tolist(), pools, leave_map)

        prog_bar = st.progress(0)
        with Pool(cpu_count()) as p:
            all_results = []
            for i in range(10):
                batch = p.map(run_single_simulation, [args] * (sims // 10))
                all_results.extend(batch)
                prog_bar.progress((i+1)*10)

        best_score, final_roster = min(all_results, key=lambda x: x[0])
        st.session_state['active_roster'] = final_roster
        st.session_state['leave_lkp'] = leave_map
        st.session_state['ph_list'] = ph
        st.session_state['fairness'] = max(0, 100 - (best_score / 200))

    if 'active_roster' in st.session_state:
        st.subheader(f"⚖️ Fairness Score: {st.session_state.get('fairness', 0):.1f}%")
        edited_df = st.data_editor(st.session_state['active_roster'], use_container_width=True, hide_index=True, column_config={"Is_Spec": None})

        # --- VIOLATION SCANNER ---
        st.subheader("⚠️ Rule Violation Alerts")
        violations, ph_list = [], st.session_state.get('ph_list', [])
        for i, row in edited_df.iterrows():
            info = st.session_state['leave_lkp'].get(row["Date"], {"absent": [], "restricted": []})
            is_we_ph = row["Date"].weekday() >= 5 or row["Date"].day in ph_list
            all_slots = ["Oncall 1", "Oncall 2", "Oncall 3", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2", "Wound Clinic"]
            names_on_day = [row[s] for s in all_slots if row[s] and str(row[s]).strip() != ""]
            
            if len(names_on_day) != len(set(names_on_day)):
                dupes = {n for n in names_on_day if names_on_day.count(n) > 1}
                violations.append(f"Day {row['Date'].day}: {', '.join(dupes)} in MULTIPLE slots!")

            for slot in ["Oncall 1", "Oncall 2", "Oncall 3", "Passive", "ELOT 1", "ELOT 2"]:
                if row[slot] in info["absent"]: violations.append(f"Day {row['Date'].day}: {row[slot]} on LEAVE but in {slot}!")
                if row[slot] in info["restricted"]: violations.append(f"Day {row['Date'].day}: {row[slot]} RESTRICTED but in {slot}!")

            if i > 0 and not is_we_ph:
                prev = {edited_df.iloc[i-1][c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {"", None}
                curr = {row[c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {"", None}
                if prev.intersection(curr): violations.append(f"Day {row['Date'].day}: {', '.join(prev.intersection(curr))} on Weekday Post-call!")

        if not violations: st.success("✅ No violations detected.")
        else: 
            for v in violations[:10]: st.error(v)

        # --- AUDIT TABLE ---
        st.subheader("📊 Duty Audit Summary")
        summary = []
        for n in staff['Staff Name'].dropna().unique():
            o_cols = ["Oncall 1", "Oncall 2", "Oncall 3"]
            wd_oc = (edited_df[~(edited_df['Date'].apply(lambda x: x.weekday()>=5 or x.day in ph_list))][o_cols] == n).sum().sum()
            we_oc = (edited_df[(edited_df['Date'].apply(lambda x: x.weekday()>=5 or x.day in ph_list))][o_cols] == n).sum().sum()
            e1, e2 = (edited_df["ELOT 1"]==n).sum(), (edited_df["ELOT 2"]==n).sum()
            summary.append({"Staff Name": n, "Oncall 1": (edited_df["Oncall 1"]==n).sum(), "Oncall 2": (edited_df["Oncall 2"]==n).sum(), "Oncall 3": (edited_df["Oncall 3"]==n).sum(),
                            "Passive": (edited_df["Passive"]==n).sum(), "Oncall (WD)": wd_oc, "Oncall (WE)": we_oc, "Total Oncall": wd_oc+we_oc,
                            "ELOT 1": e1, "ELOT 2": e2, "Total Active": wd_oc+we_oc+e1+e2, "Minor 1": (edited_df["Minor OT 1"]==n).sum(), "Minor 2": (edited_df["Minor OT 2"]==n).sum()})
        st.table(pd.DataFrame(summary).sort_values("Staff Name"))
        
        st.download_button("📥 Download Roster as CSV", edited_df.to_csv(index=False), "roster.csv", "text/csv")
