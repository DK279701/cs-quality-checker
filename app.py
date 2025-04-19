import streamlit as st
import pandas as pd
import datetime
from transformers import pipeline

# Ustawienia aplikacji
st.set_page_config(page_title="Sprawdzanie jakości CS (HuggingFace)", layout="centered")
st.title("🧠 Lokalna analiza wiadomości Customer Service (darmowe API HuggingFace)")
st.markdown("Wklej bazę wiedzy i wiadomość agenta – sprawdzimy jej jakość z wykorzystaniem darmowego modelu HuggingFace.")

# Wprowadź swój token API z HuggingFace
hf_api_key = st.text_input("🔐 Twój token API HuggingFace", type="password")

if not hf_api_key:
    st.warning("Aby korzystać z aplikacji, wklej swój token API HuggingFace.")
    st.stop()

# Inicjalizujemy model NLP (GPT-2) z HuggingFace
try:
    model_name = "distilgpt2"  # Możesz spróbować innych modeli np. GPT-2, GPT-Neo
    generator = pipeline("text-generation", model=model_name, tokenizer=model_name, use_auth_token=hf_api_key)
except Exception as e:
    st.error(f"Błąd przy ładowaniu modelu: {str(e)}")
    st.stop()

# Zapytania od użytkownika
knowledge_base = st.text_area("📘 Baza wiedzy (skopiowana z Google Sites)", height=200)
message = st.text_area("💬 Wiadomość agenta", height=200)

if st.button("🔍 Sprawdź wiadomość"):
    if not knowledge_base.strip() or not message.strip():
        st.warning("Wprowadź zarówno bazę wiedzy, jak i wiadomość agenta.")
    else:
        with st.spinner("Analiza lokalna..."):
            prompt = (
                "Jesteś ekspertem ds. jakości w obsłudze klienta. "
                "Sprawdź poniższą wiadomość agenta pod kątem zgodności z procedurami opisanymi w bazie wiedzy. "
                "Zwróć uwagę na ton, profesjonalizm i kompletność odpowiedzi. "
                "Odpowiedz po polsku.\n\n"
                f"### Baza wiedzy:\n{knowledge_base}\n\n"
                f"### Wiadomość agenta:\n{message}\n\n"  # Zakończenie ciągu
            )

            try:
                response = generator(prompt, max_length=512, num_return_sequences=1)[0]["generated_text"]
                st.success("✅ Analiza zakończona:")
                st.markdown(response)

                # Zapisanie historii analiz
                if "history" not in st.session_state:
                    st.session_state.history = []

                st.session_state.history.append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "wiadomość": message,
                    "ocena": response
                })
            except Exception as e:
                st.error(f"Błąd podczas generowania odpowiedzi: {str(e)}")
                st.stop()

if "history" in st.session_state:
    st.markdown("---")
    st.markdown("### 📋 Historia analiz")
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Pobierz CSV", csv, file_name="oceny.csv", mime="text/csv")
