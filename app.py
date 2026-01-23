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
        
        # Pull data from leave_data dictionary {Date: {"absent": [], "restricted": []}}
        day_info = leave_data.get(day, {"absent": [], "restricted": []})
        absent = day_info["absent"]
        restricted = day_info["restricted"] # No Oncall/OT people
        
        daily_occupied = set()
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool, duty_type):
            res = []
            for s in pool:
                if s in daily_occupied or s in absent: continue
                
                # GATEKEEPER: Restricted people can ONLY do Minor OT or Wound Clinic
                if s in restricted and duty_type in ["oncall", "passive", "elot"]:
                    continue
                
                if duty_type == "oncall" and s in post_call_shield:
                    continue
                res.append(s)
            return res

        # --- ALLOCATION ORDER ---
        # 1. Oncalls
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

        # 2. Passive & ELOT (Restricted staff excluded)
        if not is_spec:
            ap = get_avail(pools["passive"], "passive")
            if ap:
                row["Passive"] = ap[passive_idx % len(ap)]
                passive_idx += 1
                daily_occupied.add(row["Passive"])

        # --- 2b. ELOT (Seniority-Aware Round-Robin) ---
        if d_num in elot_days:
            # 1. Fill ELOT 1 (Seniors Only)
            ae1 = get_avail(pools["elot1"], "elot")
            p1 = None
            if ae1:
                p1 = ae1[elot_idx % len(ae1)]
                row["ELOT 1"] = p1
                daily_occupied.add(p1)
                # We don't increment elot_idx yet to keep the pairs somewhat stable, 
                # or you can increment it here—I'll increment at the end.

            # 2. Fill ELOT 2 (Qualified Staff)
            ae2 = get_avail(pools["elot2"], "elot")
            # Crucial: Ensure p1 isn't picked again for ELOT 2
            ae2_remaining = [s for s in ae2 if s != p1]
    
            if ae2_remaining:
            p2 = ae2_remaining[elot_idx % len(ae2_remaining)]
            row["ELOT 2"] = p2
            daily_occupied.add(p2)
    
            # Move the pointer forward for the next ELOT day
            elot_idx += 1

        # 3. Minor OT & Wound Clinic (Restricted staff ALLOWED)
        if d_num in minor_days:
            # 1. Fill Minor OT 1 (Experienced Staff)
            am1 = get_avail(pools["minor1"], "minor")
            pm1 = None
            if am1:
                # Using a simple random choice or you can use a separate minor_idx for Round Robin
                pm1 = random.choice(am1)
                row["Minor OT 1"] = pm1
                daily_occupied.add(pm1)

            # 2. Fill Minor OT 2 (Qualified Staff)
            am2 = get_avail(pools["minor2"], "minor")
            am2_remaining = [s for s in am2 if s != pm1]
    
            if am2_remaining:
                pm2 = random.choice(am2_remaining)
                row["Minor OT 2"] = pm2
                daily_occupied.add(pm2)

        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound")
            if aw: row["Wound Clinic"] = random.choice(aw)

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    # Fairness Check
    # Convert the list of daily rows into a temporary DataFrame for analysis
    df_temp = pd.DataFrame(roster)
    
    # 1. Count Oncalls (High Weight)
    oc_cols = ["Oncall 1", "Oncall 2", "Oncall 3"]
    oc_counts = pd.concat([df_temp[c] for c in oc_cols]).value_counts()
    
    # 2. Count ELOTs (Medium Weight)
    elot_cols = ["ELOT 1", "ELOT 2"]
    elot_counts = pd.concat([df_temp[c] for c in elot_cols]).value_counts()
    
    # 3. Calculate Standard Deviation (Spread)
    # We want both to be even, but we prioritize Oncall balance
    oc_std = np.std(oc_counts.values) if not oc_counts.empty else 100
    elot_std = np.std(elot_counts.values) if not elot_counts.empty else 100
    
    # Total Score = Penalties + (Oncall Spread * 1000) + (ELOT Spread * 500)
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
    sims = st.sidebar.slider(
    "Simulation Intensity", 
    min_value=1000, 
    max_value=50000, 
    value=10000, 
    step=1000
    )

    if st.button("Generate Roster"):
        target_month = calendar.month_name[m_idx]
        m_cfg = config[config.iloc[:, 0].astype(str) == target_month]
        def get_cfg(i): return [int(x.strip()) for x in str(m_cfg.iloc[0, i]).split(',') if x.strip().isdigit()] if not m_cfg.empty else []
        ph, elot, minor, wound = get_cfg(1), get_cfg(2), get_cfg(3), get_cfg(4)
        
        # --- PARSE LEAVE (Col D) AND RESTRICTED (Col E) ---
        leave_map = {}
        for _, r in leave.iterrows():
            d = r['Date']
            absent_names = [n.strip() for n in str(r.iloc[3]).split(',') if n.strip() and n.strip().lower() != 'nan']
            restricted_names = [n.strip() for n in str(r.iloc[4]).split(',') if n.strip() and n.strip().lower() != 'nan']
            leave_map[d] = {"absent": absent_names, "restricted": restricted_names}

        def get_names(substring):
            col = [c for c in staff.columns if substring.lower() in c.lower()]
            return staff[staff[col[0]].astype(str).str.lower() == 'yes']['Staff Name'].tolist() if col else []

        pools = {
            "o1": get_names('1st call'), 
            "o2": get_names('2nd call'), 
            "o3": get_names('3rd call'),
            "passive": get_names('Passive'), 
            "elot1": get_names('ELOT 1'),  # Senior staff only
            "elot2": get_names('ELOT 2'),  # Everyone qualified for slot 2
            "minor1": get_names('Minor 1'), 
            "minor2": get_names('Minor 2'),
            "wound": get_names('Wound')
        }
        
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
        st.session_state['fairness'] = max(0, 100 - (best_score / 200))

    if 'active_roster' in st.session_state:
        st.subheader(f"⚖️ Fairness Score: {st.session_state.get('fairness', 0):.1f}%")
        st.progress(st.session_state.get('fairness', 0) / 100)
        
        edited_df = st.data_editor(st.session_state['active_roster'], use_container_width=True, hide_index=True, column_config={"Is_Spec": None})

        # --- LIVE VIOLATION SCANNER (RECOMPILED) ---
st.subheader("⚠️ Rule Violation Alerts")
violations = []

for i, row in edited_df.iterrows():
    # 0. Contextual Data
    current_date = row["Date"]
    info = st.session_state['leave_lkp'].get(current_date, {"absent": [], "restricted": []})
    is_weekend_or_ph = current_date.weekday() >= 5 or current_date.day in ph
    
    # 1. DOUBLE ENTRY CHECK (Check if same person is in two slots on the same day)
    all_slots = ["Oncall 1", "Oncall 2", "Oncall 3", "Passive", "ELOT 1", "ELOT 2", "Minor OT 1", "Minor OT 2", "Wound Clinic"]
    names_on_day = [row[s] for s in all_slots if row[s] and str(row[s]).strip() != ""]
    
    if len(names_on_day) != len(set(names_on_day)):
        dupes = {n for n in names_on_day if names_on_day.count(n) > 1}
        violations.append(f"Day {current_date.day}: {', '.join(dupes)} assigned to MULTIPLE slots today!")

    # 2. LEAVE & RESTRICTION CHECK (Columns D & E)
    # Check Heavy Duties
    for slot in ["Oncall 1", "Oncall 2", "Oncall 3", "Passive", "ELOT 1", "ELOT 2"]:
        name = row[slot]
        if name and str(name).strip() != "":
            if name in info["absent"]:
                violations.append(f"Day {current_date.day}: {name} is on LEAVE (Col D) but in {slot}!")
            if name in info["restricted"]:
                violations.append(f"Day {current_date.day}: {name} is RESTRICTED (Col E) but in {slot}!")

    # Check Light Duties (Only Absent triggers violation)
    for slot in ["Minor OT 1", "Minor OT 2", "Wound Clinic"]:
        name = row[slot]
        if name and str(name).strip() != "" and name in info["absent"]:
            violations.append(f"Day {current_date.day}: {name} is on LEAVE (Col D) but in {slot}!")

    # 3. SMART POST-CALL CHECK (Weekday vs Weekend logic)
    if i > 0:
        prev_on = {edited_df.iloc[i-1][c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {"", None}
        curr_on = {row[c] for c in ["Oncall 1", "Oncall 2", "Oncall 3"]} - {"", None}
        conflict = prev_on.intersection(curr_on)
        
        if conflict:
            # Rule: Post-call is only a violation on Weekdays. 
            # It is PERMITTED (Prioritized) on Weekends and Public Holidays.
            if not is_weekend_or_ph:
                violations.append(f"Day {current_date.day}: {', '.join(conflict)} is on Weekday Post-call (not allowed)!")

# --- DISPLAY RESULTS ---
if not violations: 
    st.success("✅ No violations detected. This roster is safe.")
else:
    # Display up to 15 violations to keep the UI clean
    for v in violations[:15]: 
        st.error(v)
    if len(violations) > 15:
        st.warning(f"...and {len(violations)-15} more violations.")
            
        # AUDIT TABLE
st.subheader("📊 Detailed Duty Audit Summary")

summary = []
staff_names = staff['Staff Name'].dropna().unique()

# 1. Identify Weekend/PH rows
# We assume 'ph' is your list of public holiday dates
edited_df['is_weekend_ph'] = edited_df['Date'].apply(
    lambda x: x.weekday() >= 5 or x.day in ph
)

for n in staff_names:
    # --- ONCALL COUNTS ---
    o1 = (edited_df["Oncall 1"] == n).sum()
    o2 = (edited_df["Oncall 2"] == n).sum()
    o3 = (edited_df["Oncall 3"] == n).sum()
    passive = (edited_df["Passive"] == n).sum() # Position: Next to Oncall 3
    
    # --- TIMING BREAKDOWN ---
    oncall_cols = ["Oncall 1", "Oncall 2", "Oncall 3"]
    wd_oncalls = (edited_df[~edited_df['is_weekend_ph']][oncall_cols] == n).sum().sum()
    we_oncalls = (edited_df[edited_df['is_weekend_ph']][oncall_cols] == n).sum().sum()
    total_oc = wd_oncalls + we_oncalls # Position: Next to Weekend
    
    # --- ELOT & TOTAL ACTIVE ---
    e1 = (edited_df["ELOT 1"] == n).sum()
    e2 = (edited_df["ELOT 2"] == n).sum()
    # Total Active = (O1+O2+O3) + (E1+E2)
    total_active = total_oc + e1 + e2 # Position: Next to ELOT 2
    
    # --- MINOR OT ---
    m1 = (edited_df["Minor OT 1"] == n).sum()
    m2 = (edited_df["Minor OT 2"] == n).sum()

    # Define row with columns in the requested sequence
    summary.append({
        "Staff Name": n,
        "Oncall 1": o1,
        "Oncall 2": o2,
        "Oncall 3": o3,
        "Passive": passive,
        "Oncall (Weekday)": wd_oncalls,
        "Oncall (W-end/PH)": we_oncalls,
        "Total Oncall": total_oc,
        "ELOT 1": e1,
        "ELOT 2": e2,
        "Total Active (OC+ELOT)": total_active,
        "Minor OT 1": m1,
        "Minor OT 2": m2
    })

# Convert to DataFrame
audit_df = pd.DataFrame(summary).sort_values("Staff Name")

# Display the table
st.table(audit_df)
