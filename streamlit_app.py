import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from google.oauth2 import service_account
from googleapiclient.discovery import build

st.set_page_config(page_title="Client PnL Dashboard", layout="wide")
st.title("📊 Client PnL Dashboard")

# Google Sheets settings
SHEET_ID = "1eR0N0Vnq-FD5fuvikGDtK_ODXQCHv2i18y1EgtbIQKw"
SHEET_NAME = "Clients Daily PNL"  # Change if needed

# Authenticate with Service Account in Streamlit secrets
if "service_account" not in st.secrets:
    st.error("Service account not found in Streamlit secrets. Please set this in your app's Settings > Secrets.")
    st.stop()

creds = service_account.Credentials.from_service_account_info(
    dict(st.secrets["service_account"]),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)

# Connect to the Sheets API
service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()

# List all sheet names in the spreadsheet for debugging
meta = sheet.get(spreadsheetId=SHEET_ID).execute()
sheet_titles = [s['properties']['title'] for s in meta['sheets']]
st.write("✅ Sheets available in this file:", sheet_titles)

# Read the full sheet data as a list of lists
result = sheet.values().get(
    spreadsheetId=SHEET_ID,
    range=SHEET_NAME
).execute()
rows = result.get("values", [])

if not rows or len(rows) < 2:
    st.error("No data found in the Google Sheet.")
    st.stop()

# Convert to DataFrame
df_raw = pd.DataFrame(rows)

# Detect clients from row 0 (column headers)
client_row = df_raw.iloc[0]
clients = sorted(set(x for x in client_row if isinstance(x, str) and x not in ['Date', 'Day', 'Month']))

selected_client = st.selectbox("Select Client", clients)

# Identify the column index for this client's Daily PNL
client_col_index = None
for i, val in enumerate(client_row):
    if val == selected_client and df_raw.iloc[1, i] == "Daily PNL":
        client_col_index = i
        break

if client_col_index is None:
    st.warning("Client's Daily PNL column not found.")
else:
    # Extract Date + Daily PNL
    data = df_raw[[0, client_col_index]].copy()
    data.columns = ['Date', 'Daily PNL']
    data = data[2:]  # skip headers
    data['Date'] = pd.to_datetime(data['Date'], errors='coerce')
    data['Daily PNL'] = pd.to_numeric(data['Daily PNL'], errors='coerce')
    data = data.dropna()
    data = data.sort_values('Date').reset_index(drop=True)

    # Compute metrics
    pnl = data['Daily PNL']
    cum_pnl = pnl.cumsum()
    high_water_mark = cum_pnl.cummax()
    drawdown = cum_pnl - high_water_mark

    win_days = pnl[pnl > 0]
    loss_days = pnl[pnl < 0]
    total_trades = len(pnl)

    metrics = {
        "Total PNL": pnl.sum(),
        "Win Days": len(win_days),
        "Loss Days": len(loss_days),
        "Win Ratio (%)": len(win_days) / total_trades * 100 if total_trades else 0,
        "Loss Ratio (%)": len(loss_days) / total_trades * 100 if total_trades else 0,
        "Avg Profit on Win Days": win_days.mean() if not win_days.empty else 0,
        "Avg Loss on Loss Days": loss_days.mean() if not loss_days.empty else 0,
        "Total Profit on Win Days": win_days.sum(),
        "Total Loss on Loss Days": loss_days.sum(),
        "Max Profit": win_days.max() if not win_days.empty else 0,
        "Max Loss": loss_days.min() if not loss_days.empty else 0,
        "Max Drawdown": drawdown.min(),
        "Current Drawdown": drawdown.iloc[-1] if not drawdown.empty else 0,
    }

    # Streaks
    streaks = np.sign(pnl)
    win_streak = loss_streak = max_win_streak = max_loss_streak = 0
    for val in streaks:
        if val > 0:
            win_streak += 1
            loss_streak = 0
        elif val < 0:
            loss_streak += 1
            win_streak = 0
        else:
            win_streak = loss_streak = 0
        max_win_streak = max(max_win_streak, win_streak)
        max_loss_streak = max(max_loss_streak, loss_streak)

    metrics["Max Winning Streak (Days)"] = max_win_streak
    metrics["Max Losing Streak (Days)"] = max_loss_streak
    metrics["Risk Reward"] = abs(metrics["Avg Profit on Win Days"] / metrics["Avg Loss on Loss Days"] if metrics["Avg Loss on Loss Days"] != 0 else 0)
    metrics["Expectancy"] = (
        (metrics["Win Ratio (%)"] / 100) * metrics["Avg Profit on Win Days"]
        + (metrics["Loss Ratio (%)"] / 100) * metrics["Avg Loss on Loss Days"]
    )

    st.subheader("📋 Summary Metrics")
    st.dataframe(pd.DataFrame(metrics.items(), columns=["Metric", "Value"]))

    st.subheader("📈 Cumulative PNL Chart")
    fig1, ax1 = plt.subplots()
    ax1.plot(data['Date'], cum_pnl, label="Cumulative PNL")
    ax1.set_ylabel("PNL")
    ax1.set_xlabel("Date")
    ax1.grid(True)
    st.pyplot(fig1)

    st.subheader("📉 Drawdown Chart")
    fig2, ax2 = plt.subplots()
    ax2.plot(data['Date'], drawdown, label="Drawdown", color='red')
    ax2.set_ylabel("Drawdown")
    ax2.set_xlabel("Date")
    ax2.grid(True)
    st.pyplot(fig2)

    st.subheader("📆 Month-wise PNL")
    data['Month'] = data['Date'].dt.to_period('M')
    monthwise = data.groupby('Month')['Daily PNL'].sum().reset_index()
    monthwise['Month'] = monthwise['Month'].astype(str)
    st.dataframe(monthwise)
