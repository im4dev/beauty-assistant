from datetime import datetime, timedelta, timezone
import zoneinfo

def test_pm_parsing():
    print("Testing PM parsing...")
    day_to_check = datetime(2026, 5, 8, 9, 0, tzinfo=zoneinfo.ZoneInfo("America/Guayaquil"))
    slots = ["09:00 AM", "12:00 PM", "01:00 PM", "04:30 PM"]
    
    results = []
    for s in slots:
        time_part, period = s.split(' ')
        h, m = map(int, time_part.split(':'))
        if period == 'PM' and h < 12:
            h += 12
        elif period == 'AM' and h == 12:
            h = 0
        
        slot_dt = day_to_check.replace(hour=h, minute=m, second=0, microsecond=0)
        results.append(slot_dt.strftime("%Y-%m-%d %H:%M %p"))
        print(f"Parsed {s} -> {slot_dt.strftime('%H:%M %p')}")

    assert "12:00 PM" in results[1]
    assert "13:00 PM" in results[2] or "01:00 PM" in results[2]
    # Check 24h format in strings
    assert results[1].split(' ')[1] == "12:00"
    assert results[2].split(' ')[1] == "13:00"
    print("PM parsing test passed!\n")

def test_aware_now():
    print("Testing aware now for reminders...")
    now = datetime.now(timezone.utc)
    assert now.tzinfo is not None
    print(f"Aware now: {now}")
    print("Aware now test passed!\n")

if __name__ == "__main__":
    test_pm_parsing()
    test_aware_now()
