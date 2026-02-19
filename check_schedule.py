import requests
import pdfplumber
import io
import os
import sys
from datetime import datetime

# --- CONFIGURATION ---
PDF_URL = "https://www.flyaeroguard.com/wp-content/uploads/student-resources/TeamSchedule.pdf"
TARGET_NAME = "shourya"  # <-- CHANGE THIS (e.g., "Skywalker" or "Smith, J")

def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Error: Secrets missing. Cannot send Telegram message.")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def check_schedule():
    print("Downloading AeroGuard PDF...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(PDF_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        send_telegram(f"⚠️ *Bot Error:* Download failed.\n`{str(e)}`")
        sys.exit(1)

    found_flights = []

    try:
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            for i, page in enumerate(pdf.pages):
                # Extract structured tables instead of raw text
                tables = page.extract_tables()
                
                for table in tables:
                    for row in table:
                        # Clean up the row data (remove Nones and line breaks)
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        row_text = " ".join(clean_row).lower()
                        
                        # Check if your name is anywhere in this specific row
                        if TARGET_NAME.lower() in row_text:
                            # The AeroGuard table has 9 columns. If it parses perfectly:
                            if len(clean_row) >= 9 and "Activity Start" not in clean_row[0]:
                                start_time = clean_row[0]
                                stop_time = clean_row[1].split(' ')[-1] if len(clean_row[1].split(' ')) > 1 else clean_row[1]
                                status = clean_row[2]
                                instructor = clean_row[3]
                                activity = clean_row[6]
                                aircraft = clean_row[7]
                                tail_number = clean_row[8]
                                
                                # Format a clean, pilot-friendly message
                                flight_info = (
                                    f"🕒 *{start_time} - {stop_time}*\n"
                                    f"👤 *IP:* {instructor}\n"
                                    f"📚 *Activity:* {activity}\n"
                                    f"🛩️ *Aircraft:* {aircraft} (Tail: `{tail_number}`)\n"
                                    f"✅ *Status:* {status}\n"
                                )
                                found_flights.append(flight_info)
                            else:
                                # Fallback if the table row is malformed
                                fallback_text = " | ".join([c for c in clean_row if c])
                                found_flights.append(f"📌 *Pg {i+1}:* `{fallback_text}`\n")

    except Exception as e:
        send_telegram(f"⚠️ *Bot Error:* PDF Parse failed.\n`{str(e)}`")
        sys.exit(1)

    # --- SEND REPORT ---
    if found_flights:
        date_str = datetime.now().strftime("%d %b")
        msg = (f"👨‍✈️ **SCHEDULE UPDATE ({date_str})**\n"
               f"Matches for: `{TARGET_NAME}`\n\n" + 
               "\n".join(found_flights) + 
               f"\n[Open Full PDF]({PDF_URL})")
        send_telegram(msg)
        print("Schedule found and sent to Telegram.")
    else:
        print(f"No flights found for {TARGET_NAME} today.")

if __name__ == "__main__":
    check_schedule()
