import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="CS Quality Checker Debug", layout="wide")
st.title("🔍 Debug pobierania OUTBOUND wiadomości (ostatnie 7 dni)")

# --- Sidebar: Klucz API Front ---
st.sidebar.header("🔑 Klucz API")
front_token = st.sidebar.text_input("Front API Token", type="password")
if not front_token:
    st.sidebar.warning("Podaj Front API Token.")
    st.stop()

# --- Stałe Inboxy ---
INBOX_IDS = ["inb_a3xxy","inb_d2uom","inb_d2xee"]
st.sidebar.markdown("**Inboxy:**")
st.sidebar.write("- Customer Service (`inb_a3xxy`)")
st.sidebar.write("- Chat Airbnb – New (`inb_d2uom`)")
st.sidebar.write("- Chat Booking – New (`inb_d2xee`)")

# --- Zakres: ostatnie 7 dni jako Timestamp ---
seven_days_ago = pd.to_datetime(datetime.utcnow() - timedelta(days=7), utc=True)

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
                    if created_dt is not None and created_dt < seven_days_ago:
                        continue

                    raw = m.get("author") or {}
                    raw_rows.append({
                        "Message ID":       m.get("id",""),
                        "Created At":       created_dt,
                        "author.raw":       raw,
                        "author.id":        raw.get("id")        if isinstance(raw, dict) else None,
                        "author.handle":    raw.get("handle")    if isinstance(raw, dict) else None,
                        "author.username":  raw.get("username")  if isinstance(raw, dict) else None,
                        "author.name":      raw.get("name")      if isinstance(raw, dict) else None,
                    })
            cursor = js.get("_cursor")
            if not cursor:
                break
            params["cursor"] = cursor

    debug_df = pd.DataFrame(raw_rows)

    st.subheader("🔢 Surowe wiadomości outbound (ostatnie 7 dni)")
    st.write(f"Łącznie pobrano: {len(debug_df)} rekordów")
    st.dataframe(debug_df.head(10), use_container_width=True)

    st.subheader("📋 Lista kolumn w debug_df")
    st.write(list(debug_df.columns))

    st.subheader("🚩 Unikalne wartości wybranych pól")
    for col in ["author.id", "author.handle", "author.username", "author.name"]:
        if col in debug_df.columns:
            values = debug_df[col].dropna().unique().tolist()
            st.write(f"**{col}:** {values}")
        else:
            st.write(f"**{col}:** (brak kolumny)")

    st.info(
        "Sprawdź powyższe listy i określ, w którym polu są identyfikatory Twoich agentów.\n"
        "Gdy już je zidentyfikujesz, wrócimy do normalnego filtrowania po ALLOWED_IDS."
    )
    st.stop()
