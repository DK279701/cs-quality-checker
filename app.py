import streamlit as st
import requests
from bs4 import BeautifulSoup

st.title("🧪 Debug – wiadomości OUTBOUND z inboxów przez /conversations")

token = st.text_input("Front API Token", type="password")
if not token:
    st.stop()

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

INBOX_IDS = ["inb_a3xxy", "inb_d2uom", "inb_d2xee"]
all_messages = []

for inbox_id in INBOX_IDS:
    st.markdown(f"### 📥 Inbox: `{inbox_id}`")

    conv_url = f"https://api2.frontapp.com/inboxes/{inbox_id}/conversations"
    conv_resp = requests.get(conv_url, headers=headers, params={"limit": 5})  # mało na test
    if conv_resp.status_code != 200:
        st.error(f"Błąd {conv_resp.status_code}: {conv_resp.text}")
        continue

    conversations = conv_resp.json().get("_results", [])
    st.write(f"- znaleziono {len(conversations)} konwersacji")

    for conv in conversations:
        conv_id = conv["id"]
        msg_url = f"https://api2.frontapp.com/conversations/{conv_id}/messages"
        msg_resp = requests.get(msg_url, headers=headers)

        if msg_resp.status_code != 200:
            st.warning(f"Nie udało się pobrać wiadomości z {conv_id}")
            continue

        for msg in msg_resp.json().get("_results", []):
            if not msg.get("is_inbound"):  # outbound only
                body = BeautifulSoup(msg.get("body", ""), "html.parser").get_text()
                st.write(f"🟢 {msg['id']} · {body[:100]}…")
                all_messages.append(msg)

st.success(f"✅ Razem znaleziono {len(all_messages)} outboundowych wiadomości.")
