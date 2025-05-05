# CS Quality Checker – Bookinghost

Aplikacja do automatycznej oceny jakości wiadomości zespołu Customer Service z pomocą AI (GPT-4). Analizuje treść, generuje zwięzły feedback oraz oceny (1-5).

## Jak używać:
1. Wgraj plik CSV z wiadomościami (kolumny: Author, Extract).
2. Otrzymasz raport zespołowy + plik z feedbackiem dla każdej wiadomości.

## Wymagania
- Python 3.10+
- OpenAI API Key (ustaw jako zmienną środowiskową `OPENAI_API_KEY`)

## Uruchomienie lokalne
```bash
pip install -r requirements.txt
streamlit run app.py
