import streamlit as st
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Medical Roster 2026", layout="wide")

# Replace this with your actual Google Sheet ID
# It's the long string in your URL: /d/1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY/edit
SHEET_ID = "1pR3rsSXa9eUmdSylt8_U6_7TEYv7ujk1JisexuB1GUY"

# Helper function to generate CSV export URLs for specific tabs
def get_sheet_url(sheet_id, sheet_name):
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

@st.cache_data(ttl=60)
def load_all_data():
    try:
        # We fetch each tab by its name
        staff_df = pd.read_csv(get_sheet_url(SHEET_ID, "StaffList"))
        config_df = pd.read_csv(get_sheet_url(SHEET_ID, "Configuration"))
        leave_df = pd.read_csv(get_sheet_url(SHEET_ID, "LeaveRequest"))
        return staff_df, config_df, leave_df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None

# --- MAIN APP ---
st.title("🏥 Medical Roster System")

staff, config, leave = load_all_data()

if staff is not None:
    st.success("✅ Successfully connected via Public Link!")
    
    # Sidebar for Navigation
    page = st.sidebar.selectbox("Navigate", ["Staff List", "Roster Generator", "Leave Overview"])

    if page == "Staff List":
        st.subheader("Current Staffing")
        st.dataframe(staff, use_container_width=True)
        
    elif page == "Roster Generator":
        st.subheader("Generate Monthly Roster")
        # Your roster logic goes here...
        st.info("Logic processing for 2026 dates...")

    elif page == "Leave Overview":
        st.subheader("Leave Requests")
        st.write(leave)
else:
    st.warning("Please ensure your Google Sheet is set to 'Anyone with the link can view'.")
