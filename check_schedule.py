import requests
import pdfplumber
import io
import os
import sys
import re
from datetime import datetime

# --- CONFIGURATION ---
PDF_URL = "https://www.flyaeroguard.com/wp-content/uploads/student-resources/TeamSchedule.pdf"
TARGET_NAME = "shourya"  

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

def parse_flight_string(raw_string):
    """Smart parser that turns a messy PDF string into a clean UI Card."""
    # 1. Extract Dates & Times (e.g., "19 Feb 2026 13:00")
    date_pattern = r"(\d{1,2}\s[A-Z][a-z]{2}\s\d{4}\s\d{2}:\d{2})"
    dates = re.findall(date_pattern, raw_string)
    
    if len(dates) < 2:
        return f"📌 `{raw_string}`\n" # Fallback if totally broken
        
    start_dt, end_dt = dates[0], dates[1]
    
    # 2. Extract Status
    status_match = re.search(r"\b(Scheduled|Authorized|Cancelled|Ops Check In)\b", raw_string, re.IGNORECASE)
    status = status_match.group(1).title() if status_match else "Unknown Status"
    
    status_emoji = "⏳"
    if "Authorized" in status: status_emoji = "✅"
    elif "Cancelled" in status: status_emoji = "❌"
    elif "Ops" in status: status_emoji = "⚙️"
    
    # Clean up string
    remainder = raw_string.replace(start_dt, "").replace(end_dt, "")
    if status_match:
        remainder = remainder.replace(status_match.group(0), "")
        
    # 3. Extract Aircraft
    aircraft_match = re.search(r"\b(PA28-\w+|C172|PA44|DA42(?:\sNG)?|AATD|C152)\b", remainder)
    aircraft = aircraft_match.group(1) if aircraft_match else "Unknown Aircraft"
    if aircraft_match:
        remainder = remainder.replace(aircraft_match.group(0), "")
        
    # 4. Extract Instructor (or detect Solo)
    is_solo = re.search(r"\b(Solo|SOLO)\b", remainder, re.IGNORECASE)
    instructor = "Unknown IP"
    
    if is_solo:
        instructor = "🦅 SOLO FLIGHT"
    else:
        # Instructors are usually formatted as "LastName,FirstName"
        ip_match = re.search(r"\b([A-Za-z]+,[A-Za-z]+)\b", remainder)
        if ip_match:
            instructor = ip_match.group(1).replace(",", ", ")
            remainder = remainder.replace(ip_match.group(0), "")
            
    # 5. Format Times nicely
    start_parts = start_dt.split(" ")
    end_parts = end_dt.split(" ")
    time_str = f"{start_parts[3]} - {end_parts[3]}"
    
    if start_parts[0] != end_parts[0]: 
        time_str += " (+1 Day)"
        
    # 6. Whatever is left is the Lesson info
    lesson_info = " ".join(remainder.split())
    
    # 7. Build the visual card
    card = (
        f"🕒 *{time_str}*\n"
        f"{status_emoji} *Status:* {status}\n"
        f"👨‍✈️ *IP:* {instructor}\n"
        f"🛩️ *Aircraft:* {aircraft}\n"
        f"📚 *Lesson:* `{lesson_info}`\n"
    )
    return card

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
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean_row = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                        row_text = " ".join(clean_row)
                        
                        if TARGET_NAME.lower() in row_text.lower():
                            if "Activity Start" in row_text:
                                continue
                            
                            parsed_card = parse_flight_string(row_text)
                            if parsed_card not in found_flights:
                                found_flights.append(parsed_card)

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
