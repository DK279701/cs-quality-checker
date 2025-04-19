import streamlit as st
import pandas as pd
import datetime
from transformers import pipeline

# ——— Ustawienia strony ———
st.set_page_config(page_title="CS Quality (HF)", layout="centered")
st.title("🔍 Sprawdzanie jakości CS (darmowe API HuggingFace)")

# ——— Token HF ———
token = st.text_input("Wklej token HuggingFace", type="password")
if not token:
    st.warning("Potrzebny jest token HF, aby ładować model.")
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
    st.error("Błąd przy ładowaniu modelu:\n" + str(e))
    st.stop()

# ——— Wejście od użytkownika ———
kb = st.text_area("Baza wiedzy", height=150)
msg = st.text_area("Wiadomość agenta", height=150)

# ——— Generowanie i zapis historii ———
if st.button("Sprawdź teraz"):
    if not kb.strip() or not msg.strip():
        st.warning("Wypełnij obie sekcje.")
    else:
        prompt = (
            "Sprawdź tę wiadomość agenta pod kątem zgodności z procedurami i jakości:\n\n"
            "Baza:\n" + kb + "\n\n"
            "Wiadomość:\n" + msg + "\n\n"
            "Odpowiedz po polsku."
        )
        try:
            out = gen(prompt, max_length=256, num_return_sequences=1)[0]["generated_text"]
            st.markdown("### Wynik analizy")
            st.write(out)
        except Exception as e:
            st.error("Błąd generowania:\n" + str(e))
            out = ""

        # zapis historii
        hist = st.session_state.get("history", [])
        hist.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": msg,
            "result": out
        })
        st.session_state.history = hist

# ——— Wyświetlenie i eksport historii ———
if "history" in st.session_state and st.session_state.history:
    st.markdown("---")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Pobierz historię CSV", csv, "history.csv", "text/csv")
