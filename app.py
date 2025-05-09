def collect_data(token, inbox_ids, prog):
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    total_inboxes = len(inbox_ids)

    for idx, inbox in enumerate(inbox_ids, start=1):
        # ——— 1. Paginujemy konwersacje ——————————————
        convs = []
        url_conv = f"https://api2.frontapp.com/inboxes/{inbox}/conversations"
        params_c = {"limit": 100}
        while True:
            js_c, err_c = safe_get(url_conv, headers, params_c)
            if err_c:
                st.error(f"Błąd pobierania konwersacji `{inbox}`: {err_c}")
                break
            convs.extend(js_c.get("_results", []))
            cursor_c = js_c.get("_cursor")
            if not cursor_c:
                break
            params_c["cursor"] = cursor_c

        # ——— 2. Dla każdej konwersacji paginujemy wiadomości —————
        for conv in convs:
            cid = conv.get("id")
            url_msg = f"https://api2.frontapp.com/conversations/{cid}/messages"
            params_m = {"limit": 100}
            while True:
                js_m, err_m = safe_get(url_msg, headers, params_m)
                if err_m:
                    st.warning(f"Pominięcie wiadomości `{cid}` z powodu błędu: {err_m}")
                    break
                for m in js_m.get("_results", []):
                    # outbound only
                    if m.get("is_inbound", True):
                        continue
                    # autor
                    raw = m.get("author") or {}
                    author_id = raw.get("id") if isinstance(raw, dict) else None
                    if author_id not in ALLOWED_IDS:
                        continue
                    # strip HTML
                    text = BeautifulSoup(m.get("body",""), "html.parser").get_text("\n")
                    # czytelny Author
                    if isinstance(raw, dict):
                        name   = (raw.get("first_name","") + " " + raw.get("last_name","")).strip()
                        handle = raw.get("username") or raw.get("handle") or ""
                        author = f"{name} ({handle})" if handle else name
                    else:
                        author = str(raw)
                    records.append({
                        "Inbox ID":        inbox,
                        "Conversation ID": cid,
                        "Message ID":      m.get("id",""),
                        "Author ID":       author_id,
                        "Author":          author,
                        "Extract":         text
                    })
                # sprawdzamy, czy jest kolejna strona
                cursor_m = js_m.get("_cursor")
                if not cursor_m:
                    break
                params_m["cursor"] = cursor_m

        # aktualizacja paska postępu po inboxie
        prog.progress(idx / total_inboxes)

    return pd.DataFrame(records)
