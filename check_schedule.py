import requests
import pdfplumber
import io
import os
import sys
import re
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
# --- CONFIGURATION ---
PDF_URL = "https://www.flyaeroguard.com/wp-content/uploads/student-resources/TeamSchedule.pdf"
TARGET_NAME = "shourya"  
MEMORY_FILE = "last_schedule.txt"

def send_telegram(flights_data):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram secrets missing. Skipping Telegram.")
        return
        
    date_str = datetime.now().strftime("%d %b").upper()
    msg = f"🗓 **SCHEDULE: {date_str}**\n**CDT:** {TARGET_NAME.title()}\n\n"
    
    for f in flights_data:
        msg += (
            f"**{f['time']}**\n"
            f"↳ **IP:** {f['ip']}\n"
            f"↳ **AC:** {f['ac']}\n"
            f"↳ **MSN:** {f['lesson']} ({f['type']})\n"
            f"↳ **STAT:** {f['status']}\n\n"
        )
    msg += f"[Open PDF]({PDF_URL})"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True}
    requests.post(url, json=payload)

def send_trmnl(flights_data):
    webhook_url = os.environ.get("TRMNL_WEBHOOK")
    if not webhook_url:
        return

    payload = {
        "merge_variables": {
            "flights": flights_data,
            "updated_at": datetime.now().strftime("%H:%M")
        }
    }
    try:
        requests.post(webhook_url, json=payload)
    except Exception as e:
        print(f"Failed to update TRMNL: {e}")

def extract_flight_data(raw_string):
    """Parses raw text into a structured dictionary."""
    date_pattern = r"(\d{1,2}\s[A-Z][a-z]{2}\s\d{4}\s\d{2}:\d{2})"
    dates = re.findall(date_pattern, raw_string)
    
    if len(dates) < 2: return None
        
    start_dt, end_dt = dates[0], dates[1]
    
    status_match = re.search(r"\b(Scheduled|Authorized|Cancelled|Ops Check In)\b", raw_string, re.IGNORECASE)
    status = status_match.group(1).title() if status_match else "Unknown"
    
    remainder = raw_string.replace(start_dt, "").replace(end_dt, "")
    if status_match: remainder = remainder.replace(status_match.group(0), "")
        
    aircraft_match = re.search(r"\b(PA28-\w+|C172|PA44|DA42(?:\sNG)?|AATD|C152)\b", remainder)
    aircraft = aircraft_match.group(1) if aircraft_match else "Unknown"
    if aircraft_match: remainder = remainder.replace(aircraft_match.group(0), "")
        
    is_solo = re.search(r"\b(Solo|SOLO)\b", remainder, re.IGNORECASE)
    instructor = "SOLO FLIGHT" if is_solo else "Unknown IP"
    
    if not is_solo:
        ip_match = re.search(r"\b([A-Za-z]+,[A-Za-z]+)\b", remainder)
        if ip_match:
            instructor = ip_match.group(1).replace(",", ", ")
            remainder = remainder.replace(ip_match.group(0), "")
            
    activity_match = re.search(r"\b(Flight\s*/\s*[A-Za-z\s]+|Sim\s*/\s*[A-Za-z\s]+|Oral\s*/\s*[A-Za-z\s]+)\b", remainder)
    activity_type = activity_match.group(1).strip() if activity_match else ""
    if activity_match: remainder = remainder.replace(activity_match.group(0), "")

    remainder = re.sub(r"[A-Za-z0-9]+\.[A-Za-z]+\s*/\s*", "", remainder)
    lesson_info = " ".join(remainder.split())
    
    start_parts = start_dt.split(" ")
    end_parts = end_dt.split(" ")
    time_str = f"{start_parts[3]} - {end_parts[3]}"
    if start_parts[0] != end_parts[0]: time_str += " (+1D)"
        
    return {
        "time": time_str,
        "status": status,
        "ip": instructor,
        "ac": aircraft,
        "lesson": lesson_info[:20], 
        "type": activity_type.replace("Flight / ", "").replace("Sim / ", "")
    }

def check_schedule():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(PDF_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        sys.exit(1)

    flights_data = []

    try:
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        clean_row = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                        row_text = " ".join(clean_row)
                        
                        if TARGET_NAME.lower() in row_text.lower():
                            if "Activity Start" in row_text:
                                continue
                            f_data = extract_flight_data(row_text)
                            if f_data and f_data not in flights_data:
                                flights_data.append(f_data)
    except Exception as e:
        sys.exit(1)

    # --- THE BRAIN (MEMORY LOGIC) ---
    # Convert flight data to a unique hash string
    current_schedule_str = json.dumps(flights_data, sort_keys=True)
    current_fingerprint = hashlib.md5(current_schedule_str.encode()).hexdigest()

    # Read the previous fingerprint
    last_fingerprint = ""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            last_fingerprint = f.read().strip()

    if current_fingerprint == last_fingerprint:
        print("🧠 Schedule is identical to last check. Staying silent.")
        sys.exit(0)

    print("🚨 New or updated schedule detected! Sending notifications...")
    
    # Save the new fingerprint so we don't alert on it again
    with open(MEMORY_FILE, "w") as f:
        f.write(current_fingerprint)

    # Send the notifications
    if flights_data:
        send_telegram(flights_data)
        send_trmnl(flights_data)
    else:
        send_trmnl([])
        print(f"No flights found for {TARGET_NAME}.")

if __name__ == "__main__":
    check_schedule()
