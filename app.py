import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

st.set_page_config(page_title="🔄 Krok 1: Fetch OUTBOUND wiadomości", layout="wide")
st.title("🔄 Krok 1: Test pobierania wszystkich outbound-owych wiadomości")

# — Sidebar: Front API Token i zakres dat —
token = st.sidebar.text_input("Front API Token", type="password")
today = datetime.utcnow().date()
seven_days_ago = today - timedelta(days=7)
date_from, date_to = st.sidebar.date_input(
    "Zakres dat (lokalnie):", 
    value=[seven_days_ago, today],
    min_value=date(2020,1,1),
    max_value=today
)
if not token:
    st.warning("Wpisz Front API Token w sidebarze.")
    st.stop()
if date_from > date_to:
    st.sidebar.error("Data OD nie może być późniejsza niż DO.")
    st.stop()

INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]

def fetch_all_messages(token, inbox_ids, dt_from, dt_to, prog):
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    total = len(inbox_ids)

    for idx, inbox in enumerate(inbox_ids, start=1):
        # 1) pobierz listę konwersacji paginowana
        convs = []
        url_c = f"https://api2.frontapp.com/inboxes/{inbox}/conversations"
        params = {"limit": 100}
        while True:
            r = requests.get(url_c, headers=headers, params=params); r.raise_for_status()
            js = r.json()
            convs.extend(js.get("_results", []))
            cursor = js.get("_cursor")
            if not cursor: break
            params["cursor"] = cursor

        # 2) dla każdej konwersacji pobierz wiadomości
        for c in convs:
            cid = c["id"]
            url_m = f"https://api2.frontapp.com/conversations/{cid}/messages"
            r2 = requests.get(url_m, headers=headers); r2.raise_for_status()
            for m in r2.json().get("_results", []):
                if m.get("is_inbound", True):
                    continue
                # data i filtr
                dt = pd.to_datetime(m.get("created_at"), utc=True).date()
                if dt < dt_from or dt > dt_to:
                    continue
                # body -> text
                text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                records.append({
                    "Created_date": dt,
                    "Inbox":        inbox,
                    "Message ID":   m["id"],
                    "Extract":      text
                })
        prog.progress(idx/total)

    return pd.DataFrame(records)

# — Ui —
prog = st.sidebar.progress(0.0)
if st.button("▶️ Pobierz wiadomości"):
    with st.spinner("Pobieram…"):
        df = fetch_all_messages(token, INBOX_IDS, date_from, date_to, prog)
    if df.empty:
        st.warning("Nie znaleziono żadnych wiadomości w zadanym okresie.")
    else:
        st.success(f"Pobrano {len(df)} wiadomości.")
        st.dataframe(df.head(10), use_container_width=True)
