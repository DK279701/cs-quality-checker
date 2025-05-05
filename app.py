import streamlit as st
import pandas as pd
import openai
import time

# ⚡️ Wprowadzenie API Key (nie zapisuje tego!)
openai_api_key = st.text_input("Wklej swój OpenAI API Key", type="password")

# Ὄ2 Wczytanie pliku CSV
st.title("💼 System oceny jakości i produktywności agentów Bookinghost")
uploaded_file = st.file_uploader("Wgraj plik CSV z Front (dane wiadomości)", type="csv")

if uploaded_file and openai_api_key:
    df = pd.read_csv(uploaded_file)

    if 'Author' not in df.columns or 'Extract' not in df.columns:
        st.error("Brakuje kolumny 'Author' lub 'Extract' w pliku CSV")
    else:
        st.success("Plik poprawnie wczytany! Rozpoczynam ocenianie wiadomości...")

        results = []
        for idx, row in df.iterrows():
            message = row['Extract']
            author = row['Author']
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    api_key=openai_api_key,
                    messages=[
                        {"role": "system", "content": "Jesteś ekspertem ds. jakości obsługi klienta Bookinghost. Oceń poniższą wiadomość według standardów firmy. Odpowiedz TYLKO TAK lub NIE oraz uzasadnij ocenę."},
                        {"role": "user", "content": message}
                    ]
                )
                gpt_answer = response.choices[0].message.content
            except Exception as e:
                gpt_answer = f"Błąd: {e}"

            results.append({
                "Author": author,
                "Extract": message,
                "GPT-ocena": gpt_answer
            })
            time.sleep(1.2)  # uniknij przekroczenia limitu API

        result_df = pd.DataFrame(results)
        st.dataframe(result_df)

        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button("🔧 Pobierz wyniki jako CSV", data=csv, file_name="ocena_jakosci.csv", mime='text/csv')
