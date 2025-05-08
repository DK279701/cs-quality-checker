import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="CS Quality Checker Debug", layout="wide")
st.title("🔍 Debug pobierania OUTBOUND wiadomości (ostatnie 7 dni)")

# --- Sidebar: klucze API ---
st.sidebar.header("🔑 Klucze API")
front_token = st.sidebar.text_input("Front API Token", type="password")
if not front_token:
    st.sidebar.warning("Podaj Front API Token.")
    st.stop()

# --- Stałe inboxy ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
st.sidebar.markdown("**Inboxy:**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# --- Zakres czasowy: ostatnie 7 dni ---
now = datetime.utcnow()
seven_days_ago = now - timedelta(days=7)

if st.button("▶️ Debug: pobierz surowe outbound z ostatnich 7 dni"):
    raw_rows = []
    for inbox in INBOX_IDS:
        params = {"inbox_id": inbox, "page_size": 100}
        while True:
            resp = requests.get(
                "https://api2.frontapp.com/conversations",
                headers={"Authorization": f"Bearer {front_token}"},
                params=params
            )
            resp.raise_for_status()
            js = resp.json()
            for conv in js.get("_results", []):
                cid = conv["id"]
                msgs = requests.get(
                    f"https://api2.frontapp.com/conversations/{cid}/messages",
                    headers={"Authorization": f"Bearer {front_token}"}
                )
                msgs.raise_for_status()
                for m in msgs.json().get("_results", []):
                    # tylko outbound
                    if m.get("is_inbound", True):
                        continue
                    # created_at
                    created = m.get("created_at")
                    created_dt = pd.to_datetime(created, utc=True) if created else None
                    if created_dt and created_dt < seven_days_ago:
                        continue
                    raw = m.get("author") or {}
                    raw_rows.append({
                        "Message ID":     m.get("id",""),
                        "Created At":     created_dt,
                        "author.raw":     raw,
                        "author.id":      raw.get("id")         if isinstance(raw, dict) else None,
                        "author.handle":  raw.get("handle")     if isinstance(raw, dict) else None,
                        "author.username":raw.get("username")   if isinstance(raw, dict) else None,
                        "author.name":    raw.get("name")       if isinstance(raw, dict) else None,
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    debug_df = pd.DataFrame(raw_rows)
    st.subheader("🔢 Surowe wiadomości outbound (ostatnie 7 dni)")
    st.write(f"Łącznie pobrano: {len(debug_df)} rekordów")
    st.dataframe(debug_df.head(10))

    st.subheader("🚩 Unikalne wartości pola author.id / handle / username / name")
    st.write("author.id:",   debug_df["author.id"].unique().tolist())
    st.write("author.handle:", debug_df["author.handle"].unique().tolist())
    st.write("author.username:", debug_df["author.username"].unique().tolist())
    st.write("author.name:", debug_df["author.name"].unique().tolist())

    st.info("Sprawdź powyższe listy i zobacz, które pola zawierają identyfikatory agentów.\n"
            "Gdy już to ustalisz, wrócimy do filtrowania po ALLOWED_IDS.")
