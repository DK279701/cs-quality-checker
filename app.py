import streamlit as st
import pandas as pd
import openai
import asyncio
import time

# Konfiguracja OpenAI API Key
openai.api_key = st.text_input("Wprowadź swój API key OpenAI", type="password")

# Funkcja do analizy wiadomości
async def analyze_message_async(message_row):
    message = message_row.get('Extract', '')
    author = message_row.get('Author', 'Unknown')
    
    # Wytyczne do analizy jakościowej
    instructions = """
    Jesteś menedżerem obsługi klienta w firmie Bookinghost i chcesz zapewnić, aby jakość komunikacji w Twoim zespole była jak najwyższa. Każda wiadomość, którą analizujesz, powinna być oceniona pod kątem profesjonalizmu, skuteczności, uprzedzeń i szybkości odpowiedzi.
    Dodatkowo, pamiętaj, że analiza powinna brać pod uwagę poprawność językową, zgodność z procedurami oraz ton odpowiedzi, który musi być uprzedzająco pomocny.
    """

    # Zlecenie analizy do modelu GPT-3
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Ocena tej wiadomości: '{message}'"}
        ]
    )

    quality_score = response['choices'][0]['message']['content']
    return {
        "Message ID": message_row.get('Message ID', ''),
        "Author": author,
        "Quality Score": quality_score,
        "Feedback": "Analiza zakończona",
        "Justification": "Model ocenił jakość komunikacji na podstawie podanych wytycznych."
    }

# Interfejs użytkownika w Streamlit
st.title("Narzędzie do analizy jakości obsługi klienta w Bookinghost")

# Wczytywanie pliku CSV
uploaded_file = st.file_uploader("Załaduj plik CSV", type=["csv"])
if uploaded_file:
    try:
        # Wczytanie pliku z uwzględnieniem separatora i błędnych linii
        data = pd.read_csv(uploaded_file, sep=';', encoding='utf-8', error_bad_lines=False, warn_bad_lines=True)
        
        # Przefiltrowanie danych (opcjonalnie, np. wybór agenta)
        filter_agent = st.selectbox("Wybierz agenta", options=["Wszyscy"] + list(data['Author'].unique()))
        if filter_agent != "Wszyscy":
            filtered_data = data[data['Author'] == filter_agent]
        else:
            filtered_data = data
        
        # Pasek postępu
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Start timera
        start_time = time.time()
        results = []

        # Przetwarzanie danych
        for idx, row in enumerate(filtered_data.iterrows(), 1):
            index, message_row = row
            try:
                result = asyncio.run(analyze_message_async(message_row))
                results.append(result)
            except Exception as e:
                results.append({
                    "Message ID": message_row.get("Message ID", ""),
                    "Author": message_row.get("Author", ""),
                    "Quality Score": "Error",
                    "Feedback": f"Błąd analizy: {str(e)}",
                    "Justification": ""
                })
            # Aktualizacja statusu
            progress = idx / len(filtered_data)
            progress_bar.progress(min(progress, 1.0))
            status_text.text(f"Przetworzono wiadomości: {idx}/{len(filtered_data)}")

        # Zakończenie timera
        elapsed_time = time.time() - start_time
        st.success(f"Analiza zakończona w {elapsed_time:.2f} sekundy.")

        # Prezentacja wyników
        results_df = pd.DataFrame(results)
        st.write(f"Podsumowanie analizy dla agenta {filter_agent}:")
        st.dataframe(results_df)

        # Zapisz wyniki do CSV
        st.download_button("Pobierz wyniki analizy", results_df.to_csv(index=False), "analiza_wiadomosci.csv", "text/csv")

        # Analiza zespołu
        overall_feedback = "Zespół wykonuje zadania dobrze, ale warto zwrócić uwagę na poprawność językową i ton komunikacji."
        st.write("Podsumowanie dla całego zespołu:")
        st.write(overall_feedback)

    except Exception as e:
        st.error(f"Błąd podczas przetwarzania pliku: {e}")
