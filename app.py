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

# --- 2. THE SIMULATION CORE (WITH GATEKEEPER LOGIC) ---
def run_single_simulation(args):
    days, ph_days, elot_days, minor_days, wound_days, all_staff, pools, leave_lookup = args
    roster, total_penalties = [], 0
    post_call_shield = set() 
    weekend_team = []
    passive_idx = random.randint(0, 100)

    for day in days:
        d_num = day.day
        is_sat, is_sun = day.weekday() == 5, day.weekday() == 6
        is_ph = d_num in ph_days
        is_spec = (is_sat or is_sun or is_ph)
        
        # requests_today is now a dict: {Name: RequestType}
        requests_today = leave_lookup.get(day, {}) 
        daily_occupied = set()
        
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool, duty_type):
            res = []
            for s in pool:
                if s in daily_occupied: continue
                
                req = str(requests_today.get(s, "")).lower()
                
                # RULE 1: Total Absence (AL/Leave/MC)
                if any(word in req for word in ["leave", "al", "mc"]):
                    continue
                
                # RULE 2: "No Oncall/OT" Restricted People
                # They are blocked from Oncall, Passive, and ELOT
                if "no" in req and duty_type in ["oncall", "passive", "elot"]:
                    continue
                
                # RULE 3: Post-Call Shield for Oncalls
                if duty_type == "oncall" and s in post_call_shield:
                    continue
                
                res.append(s)
            return res

        # --- ONCALL LOGIC ---
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

        # --- PASSIVE (Weekday Only) ---
        if not is_spec:
            ap = get_avail(pools["passive"], "passive")
            if ap:
                row["Passive"] = ap[passive_idx % len(ap)]
                passive_idx += 1
                daily_occupied.add(row["Passive"])

        # --- OT DUTIES ---
        # ELOT (Restricted)
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if len(ae) >= 2:
                picks = random.sample(ae, 2)
                row["ELOT 1"], row["ELOT 2"] = picks[0], picks[1]
                daily_occupied.update(picks)
            elif ae: row["ELOT 1"] = ae[0]

        # Minor OT (Open to "No" requests)
        if d_num in minor_days:
            am = get_avail(pools["minor"], "minor")
            if len(am) >= 2:
                picks = random.sample(am, 2)
                row["Minor OT 1"], row["Minor OT 2"] = picks[0], picks[1]
                daily_occupied.update(picks)

        # Wound Clinic (Open to "No" requests)
        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound")
            if aw: row["Wound Clinic"] = random.choice(aw)

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    df_temp = pd.DataFrame(roster)
    oncall_counts = pd.concat([df_temp[c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]]).value_counts()
    oncall_std = np.std(oncall_counts.values) if not oncall_counts.empty else 100
    elot_counts = pd.concat([df_temp["ELOT 1"], df_temp["ELOT 2"]]).value_counts()
    elot_std = np.std(elot_counts.values) if not elot_counts.empty else 0
    score = total_penalties + (oncall_std * 1000) + (elot_std * 200)
    
    return score, df_temp

# --- 3. UI & APP LOGIC ---
st.set_page_config(page_title="HPC AI Roster", layout="wide")
st.title("🏥 Medical Roster: Group & Gatekeeper Optimizer")

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
        
        def get_names(substring):
            col = [c for c in staff.columns if substring.lower() in c.lower()]
            if not col: return []
            return staff[staff[col[0]].astype(str).str.lower() == 'yes']['Staff Name'].tolist()

        pools = {
            "o1": get_names('1st call'), "o2": get_names('2nd call'), "o3": get_names('3rd call'),
            "passive": get_names(staff.columns[4]), 
            "elot": get_names('ELOT'), "minor": get_names('Minor'), "wound": get_names('Wound')
        }
        
        days = [date(2026, m_idx, d) for d in range(1, calendar.monthrange(2026, m_idx)[1] + 1)]
        
        # Advanced Leave Lookup: {Date: {Name: Type}}
        leave_map = {}
        for _, r in leave.iterrows():
            d, name, req = r['Date'], str(r.iloc[0]).strip(), str(r.iloc[3]).strip().lower()
            if d not in leave_map: leave_map[d] = {}
            leave_map[d][name] = req
            
        args = (days, ph, elot, minor, wound, staff['Staff Name'].tolist(), pools, leave_map)

        prog_bar = st.progress(0)
        status_text = st.empty()
        with Pool(cpu_count()) as p:
            all_results = []
            for i in range(10):
                batch = p.map(run_single_simulation, [args] * (sims // 10))
                all_results.extend(batch)
                prog_bar.progress((i + 1) * 10)
                status_text.text(f"Optimizing... {(i+1)*10}%")

        _, final_roster = min(all_results, key=lambda x: x[0])
        st.session_state['active_roster'] = final_roster
        st.session_state['leave_lkp'] = leave_map

    if 'active_roster' in st.session_state:
        st.subheader("✏️ Manual Shift Adjuster")
        edited_df = st.data_editor(st.session_state['active_roster'], use_container_width=True, hide_index=True, column_config={"Is_Spec": None})

        # --- ENHANCED LIVE VIOLATION SCANNER ---
        st.subheader("⚠️ Live Rule Violation Alerts")
        violations = []
        for i, row in edited_df.iterrows():
            today_reqs = st.session_state['leave_lkp'].get(row["Date"], {})
            
            # Check Restrictions (Oncall, Passive, ELOT)
            for slot in ["Oncall 1", "Oncall 2", "Oncall 3", "Passive", "ELOT 1", "ELOT 2"]:
                name = row[slot]
                if name:
                    req = today_reqs.get(name, "")
                    if any(word in req for word in ["leave", "al", "mc"]):
                        violations.append(f"Day {row['Date'].day}: {name} is on LEAVE but assigned {slot}!")
                    elif "no" in req:
                        violations.append(f"Day {row['Date'].day}: {name} has a 'No Oncall/OT' request and cannot do {slot}!")

            # Check Minor/Wound for Leave only
            for slot in ["Minor OT 1", "Minor OT 2", "Wound Clinic"]:
                name = row[slot]
                if name and any(word in today_reqs.get(name, "") for word in ["leave", "al", "mc"]):
                    violations.append(f"Day {row['Date'].day}: {name} is on LEAVE but assigned {slot}!")

            # Post-Call Check
            if i > 0:
                prev_on = {edited_df.iloc[i-1][c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {""}
                curr_on = {row[c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {""}
                conflict = prev_on.intersection(curr_on)
                if conflict: violations.append(f"Day {row['Date'].day}: {', '.join(conflict)} is on Post-call duty!")

        if not violations: st.success("All rules followed.")
        else:
            for v in violations[:15]: st.error(v)

        # AUDIT SUMMARY
        st.subheader("📊 Duty Audit Summary")
        summary = []
        for n in staff['Staff Name'].dropna().unique():
            o1, o2, o3 = (edited_df["Oncall 1"] == n).sum(), (edited_df["Oncall 2"] == n).sum(), (edited_df["Oncall 3"] == n).sum()
            wknd = (edited_df[edited_df["Is_Spec"] == True][["Oncall 1", "Oncall 2", "Oncall 3"]] == n).sum().sum()
            summary.append({"Staff Name": n, "O1": o1, "O2": o2, "O3": o3, "Total": o1+o2+o3, "Weekend/PH": wknd, "ELOT": (edited_df[["ELOT 1", "ELOT 2"]] == n).sum().sum(), "Minor OT": (edited_df[["Minor OT 1", "Minor OT 2"]] == n).sum().sum()})
        st.table(pd.DataFrame(summary))
