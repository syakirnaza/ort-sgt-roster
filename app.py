import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Medical Roster Generator")

st.title("🏥 Medical On-Call Dashboard Generator")
st.write("Adjust settings in the sidebar and click **Generate**.")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Roster Settings")
month = st.sidebar.selectbox("Month", ["February"])
year = st.sidebar.number_input("Year", value=2025)

staff_list = st.sidebar.text_area("Staff Names (Comma separated)", 
    "Akram, Syahmi, Simon, Aishah, Syakir, Lemuel, Yoges, Fatiha, Aina, Thivya, Arif, Hefiy, Johnny")

if st.sidebar.button("Generate Final Roster"):
    # --- LOGIC ENGINE ---
    dates = pd.date_range(start=f"{year}-02-01", periods=28)
    df = pd.DataFrame({"Date": dates.day, "Day": dates.day_name()})
    
    # Logic to fill calls (Simulated for this example)
    df["1st Call"] = "Staff A"
    df["2nd Call"] = "Staff B"
    df["ELOT 1"] = "Yoges"
    
    # --- DISPLAY DASHBOARD ---
    def color_rows(row):
        # Light Green for Weekends & Public Holidays (Feb 2, 17, 18, 19)
        ph = [2, 17, 18, 19]
        if row.Day in ['Saturday', 'Sunday'] or row.Date in ph:
            return ['background-color: #e8f5e9'] * len(row)
        return [''] * len(row)

    st.table(df.style.apply(color_rows, axis=1))
    
    # Download Button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download as CSV", csv, "roster.csv", "text/csv")
