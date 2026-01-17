import streamlit as st
import pandas as pd
import calendar
import random
import numpy as np
from datetime import date, timedelta

# --- 1. DATA LOADING ENGINE (UNCHANGED) ---
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
        st.error(f"Error connecting to Google Sheets: {e}")
        return None, None, None

# --- 2. SINGLE ROSTER GENERATION LOGIC (UPDATED FOR SAFETY) ---
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
    passive_idx = random.randint(0, 100)
    
    # Trackers for Weekend Continuity
    weekend_team = [] 
    prev_sat_o1 = None
    post_call_shield = set()

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

        # RESET trackers for the day
        daily_occupied = set()
        row = {"Date": day, "Day": day.strftime("%A"), "Is_Spec": is_spec,
               "Oncall 1": "", "Oncall 2": "", "Oncall 3": "", "Passive": "", 
               "ELOT 1": "", "ELOT 2": "", "Minor OT 1": "", "Minor OT 2": "", "Wound Clinic": ""}

        def get_avail(pool, duty_type):
            # Base availability: Not on leave and not already picked for another role today
            res = [s for s in pool if s not in absent and s not in daily_occupied]
            if duty_type in ["oncall", "passive", "elot"]:
                res = [s for s in res if s not in restricted]
            if duty_type == "elot":
                res = [s for s in res if s not in post_call_shield]
            return res

        # --- ONCALL LOGIC (The Core Fix) ---
        if is_sun and len(weekend_team) == 3:
            # SUNDAY: Mandatory reuse of Saturday's team
            sun_pool = [s for s in weekend_team if s not in absent and s not in restricted]
            if len(sun_pool) < 3:
                total_penalties += 2000 # Leave broke the weekend group
                sun_pool = get_avail(pools["o1"], "oncall") # Emergency fallback
            
            random.shuffle(sun_pool)
            # Rotation Rule: Sunday O1 must be different from Saturday O1
            if sun_pool[0] == prev_sat_o1 and len(sun_pool) > 1:
                sun_pool[0], sun_pool[1] = sun_pool[1], sun_pool[0]
            
            for i, call in enumerate(["Oncall 1", "Oncall 2", "Oncall 3"]):
                if i < len(sun_pool):
                    row[call] = sun_pool[i]
                    daily_occupied.add(sun_pool[i])
        else:
            # WEEKDAYS, SATURDAY, OR PH: Fresh Selection
            if is_sat: weekend_team = []
            
            for call_key, pool_key in [("Oncall 1", "o1"), ("Oncall 2", "o2"), ("Oncall 3", "o3")]:
                # Only do Oncall 3 on Specials
                if call_key == "Oncall 3" and not is_spec: continue
                
                avail = get_avail(pools[pool_key], "oncall")
                if avail:
                    pick = random.choice(avail)
                    row[call_key] = pick
                    daily_occupied.add(pick)
                    if is_sat: 
                        weekend_team.append(pick)
                        if call_key == "Oncall 1": prev_sat_o1 = pick
                else: total_penalties += 5000

        # --- ELOT, MINOR, WOUND (Respects daily_occupied) ---
        if d_num in elot_days:
            ae = get_avail(pools["elot"], "elot")
            if is_sat and ae: 
                row["ELOT 1"] = random.choice(ae)
                daily_occupied.add(row["ELOT 1"])
            elif len(ae) >= 2:
                picks = random.sample(ae, 2)
                row["ELOT 1"], row["ELOT 2"] = picks[0], picks[1]
                daily_occupied.update(picks)

        if d_num in minor_days:
            am = get_avail(pools["minor"], "minor_ot")
            if len(am) >= 2:
                picks = random.sample(am, 2)
                row["Minor OT 1"], row["Minor OT 2"] = picks[0], picks[1]
                daily_occupied.update(picks)

        if d_num in wound_days:
            aw = get_avail(pools["wound"], "wound_clinic")
            if aw: 
                row["Wound Clinic"] = random.choice(aw)
                daily_occupied.add(row["Wound Clinic"])

        # --- Passive ---
        ap = get_avail(all_staff, "passive")
        if ap:
            row["Passive"] = ap[passive_idx % len(ap)]
            passive_idx += 1
            daily_occupied.add(row["Passive"])

        post_call_shield = {row["Oncall 1"], row["Oncall 2"], row["Oncall 3"]} - {""}
        roster.append(row)

    # --- EQUALITY SCORING ---
    df = pd.DataFrame(roster)
    spec_df = df[df["Is_Spec"]]
    weekend_counts = pd.concat([spec_df["Oncall 1"], spec_df["Oncall 2"], spec_df["Oncall 3"]]).value_counts().reindex(all_staff, fill_value=0)
    total_counts = pd.concat([df["Oncall 1"], df["Oncall 2"], df["Oncall 3"]]).value_counts().reindex(all_staff, fill_value=0)
    
    total_score = total_penalties + (np.std(weekend_counts) * 200) + (np.std(total_counts) * 150)
    return df, total_score

# --- 3. OPTIMIZER & UI (UNCHANGED) ---
def optimize_roster(m_idx, year, staff, leave, config, iterations):
    best_df, best_score = None, float('inf')
    bar = st.progress(0)
    status = st.empty()
    for i in range(1, iterations + 1):
        df, score = run_simulation(m_idx, year, staff, leave, config)
        if score < best_score:
            best_score, best_df = score, df
        if best_score == 0: break 
        if i % 1000 == 0:
            bar.progress(i/iterations)
            status.info(f"Analyzing {i}/{iterations} runs. Fairness Gap: {best_score:.2f}")
    return best_df

st.set_page_config(page_title="HPC Fairness Optimizer", layout="wide")
st.title("🏥 Medical Roster: Absolute Equality & Safety Optimizer")

SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"
staff, leave, config = load_all_data(SHEET_ID)

if staff is not None:
    m_name = st.sidebar.selectbox("Month", [m for m in list(calendar.month_name) if m])
    m_idx = list(calendar.month_name).index(m_name)
    sims = st.sidebar.select_slider("Intensity", options=[1000, 10000, 50000], value=10000)

    if st.button("Generate Mathematically Fair Roster"):
        final_df = optimize_roster(m_idx, 2026, staff, leave, config, sims)
        st.dataframe(final_df.drop(columns=["Is_Spec"]), use_container_width=True)

        st.subheader("📊 Duty Audit")
        summary_data = []
        for name in staff['Staff Name'].dropna().unique():
            o1, o2, o3 = (final_df["Oncall 1"]==name).sum(), (final_df["Oncall 2"]==name).sum(), (final_df["Oncall 3"]==name).sum()
            spec = final_df[final_df["Is_Spec"] == True]
            w_count = (spec["Oncall 1"]==name).sum() + (spec["Oncall 2"]==name).sum() + (spec["Oncall 3"]==name).sum()
            summary_data.append({
                "Staff Member": name, "Oncall 1": o1, "Oncall 2": o2, "Oncall 3": o3,
                "TOTAL ONCALL": o1+o2+o3, "WEEKEND/PH ONCALL": w_count,
                "ELOT": (final_df["ELOT 1"]==name).sum() + (final_df["ELOT 2"]==name).sum(),
                "Passive": (final_df["Passive"]==name).sum()
            })
        st.table(pd.DataFrame(summary_data))
        
        max_w, min_w = pd.DataFrame(summary_data)["WEEKEND/PH ONCALL"].max(), pd.DataFrame(summary_data)["WEEKEND/PH ONCALL"].min()
        st.metric("Weekend Load Gap", f"{max_w - min_w} Shift(s)")
