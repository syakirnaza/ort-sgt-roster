import streamlit as st
import pandas as pd
import calendar
from datetime import datetime

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Medical Roster 2026", layout="wide")

# Replace with your actual Google Sheet ID
SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

def get_sheet_url(sheet_id, sheet_name):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

@st.cache_data(ttl=60)
def load_all_data():
    try:
        staff_df = pd.read_csv(get_sheet_url(SHEET_ID, "StaffList"))
        leave_df = pd.read_csv(get_sheet_url(SHEET_ID, "LeaveRequest"))
        # Ensure date columns are actually dates
        leave_df['Date'] = pd.to_datetime(leave_df['Date']).dt.date
        return staff_df, leave_df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

# --- 2. ROSTER LOGIC ---
def generate_roster(month, year, staff_df, leave_df):
    num_days = calendar.monthrange(year, month)[1]
    days = [datetime(year, month, d).date() for d in range(1, num_days + 1)]
    
    roster_data = []
    staff_list = staff_df['Name'].tolist()
    
    for i, day in enumerate(days):
        # 1. Check who is on leave today
        on_leave = leave_df[leave_df['Date'] == day]['Name'].tolist()
        
        # 2. Filter available staff
        available_staff = [s for s in staff_list if s not in on_leave]
        
        # 3. Simple Rotation Logic (Assigns staff based on index)
        if available_staff:
            assigned_staff = available_staff[i % len(available_staff)]
        else:
            assigned_staff = "⚠️ SHORTAGE"
            
        roster_data.append({
            "Date": day.strftime("%Y-%m-%d"),
            "Day": day.strftime("%A"),
            "Assigned Staff": assigned_staff,
            "On Leave": ", ".join(on_leave) if on_leave else "None"
        })
    
    return pd.DataFrame(roster_data)

# --- 3. MAIN INTERFACE ---
st.title("🏥 Medical Roster System - 2026")

staff, leave = load_all_data()

if staff is not None:
    menu = st.sidebar.radio("Menu", ["Staff Overview", "Generate Roster"])

    if menu == "Staff Overview":
        st.subheader("📋 Personnel List")
        st.dataframe(staff, use_container_width=True)
        
        st.subheader("🗓️ Logged Leave Requests")
        st.write(leave)

    elif menu == "Generate Roster":
        st.subheader("⚙️ Roster Generator Settings")
        
        col1, col2 = st.columns(2)
        with col1:
            month_name = st.selectbox("Select Month", list(calendar.month_name)[1:])
            month = list(calendar.month_name).index(month_name)
        with col2:
            year = st.number_input("Year", min_value=2026, max_value=2027, value=2026)

        if st.button("Generate Monthly Roster"):
            final_roster = generate_roster(month, year, staff, leave)
            
            st.success(f"Roster for {month_name} {year} generated!")
            
            # Display with coloring for weekends
            def highlight_weekends(s):
                return ['background-color: #f0f2f6' if s.Day in ['Saturday', 'Sunday'] else '' for _ in s]
            
            st.dataframe(final_roster.style.apply(highlight_weekends, axis=1), use_container_width=True)
            
            # Download Button
            csv = final_roster.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Roster as CSV", csv, f"roster_{month_name}_{year}.csv", "text/csv")
