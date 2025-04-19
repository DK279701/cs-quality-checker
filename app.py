import streamlit as st
import pandas as pd
import datetime
from transformers import pipeline

# ——— Konfiguracja strony ———
st.set_page_config(page_title="CS Quality (HF)", layout="centered")
st.title("Sprawdzanie jakości CS (darmowe API HuggingFace)")

# ——— Token HuggingFace ———
token = st.text_input("Token HF", type="password")
if not token:
    st.stop()

# ——— Ładowanie modelu ———
try:
    gen = pipeline(
        "text-generation",
        model="distilgpt2",
        tokenizer="distilgpt2",
        use_auth_token=token
    )
except Exception as e:
    st.error("Błąd ładowania modelu:\n" + str(e))
    st.stop()

# ——— Wejście użytkownika ———
kb = st.text_area("Baza wiedzy", height=150)
msg = st.text_area("Wiadomość agenta", height=150)

# ——— Analiza i zapis historii ———
if st.button("Sprawdź"):
    if not kb.strip() or not msg.strip():
        st.warning("Uzupełnij bazę i wiadomość.")
    else:
        prompt = f"""Sprawdź tę wiadomość agenta pod kątem procedur i jakości:\n\nBaza:\n{kb}\n\nWiadomość:\n{msg}\n\nOdpowiedz po polsku."""
        try:
            out = gen(prompt, max_length=256, num_return_sequences=1)[0]["generated_text"]
            st.markdown("**Wynik:**\n\n" + out)
        except Exception as e:
            st.error("Błąd generowania:\n" + str(e))

        # historia
        hist = st.session_state.get("history", [])
        hist.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": msg,
            "result": out
        })
        st.session_state.history = hist

# ——— Wyświetlenie i pobranie historii ———
if "history" in st.session_state:
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz CSV", csv, "history.csv", "text/csv")
