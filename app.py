import streamlit as st
import pandas as pd
import datetime
from transformers import pipeline

st.set_page_config(page_title="Sprawdzanie jakości CS (HuggingFace)", layout="centered")
st.title("🧠 Analiza wiadomości CS z darmowym API HuggingFace")
st.markdown("Wklej bazę wiedzy i wiadomość agenta – sprawdzimy jej jakość.")

hf_api_key = st.text_input("🔐 Token API HuggingFace", type="password")
if not hf_api_key:
    st.warning("Wklej token API z HuggingFace, żeby działało.")
    st.stop()

# Ładujemy model
try:
    generator = pipeline(
        "text-generation",
        model="distilgpt2",
        tokenizer="distilgpt2",
        use_auth_token=hf_api_key
    )
except Exception as e:
    st.error(f"❌ Błąd przy ładowaniu modelu:\n{e}")
    st.stop()

knowledge_base = st.text_area("📘 Baza wiedzy", height=200)
message = st.text_area("💬 Wiadomość agenta", height=200)

if st.button("🔍 Sprawdź"):
    if not knowledge_base or not message:
        st.warning("Uzupełnij bazę wiedzy i wiadomość agenta.")
    else:
        with st.spinner("Analiza..."):
            prompt = f"""Jesteś ekspertem ds. jakości w obsłudze klienta.
Na podstawie tej bazy wiedzy sprawdź, czy wiadomość agenta jest zgodna z procedurami.
Jeśli nie, wskaż, co poprawić. Oceń ton, profesjonalizm i kompletność odpowiedzi.

### Baza wiedzy:
{knowledge_base}

### Wiadomość agenta:
{message}

Odpowiedz po polsku."""

            try:
                out = generator(prompt, max_length=512, num_return_sequences=1)[0]["generated_text"]
                st.success("✅ Analiza zakończona:")
                st.markdown(out)

                # zapisujemy historię
                if "history" not in st.session_state:
                    st.session_state.history = []
                st.session_state.history.append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "wiadomość": message,
                    "ocena": out
                })
            except Exception as e:
                st.error(f"❌ Błąd przy generowaniu:\n{e}")

# wyświetlamy historię
if "history" in st.session_state and st.session_state.history:
    st.markdown("---")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Pobierz CSV", csv, "analizy.csv", "text/csv")
