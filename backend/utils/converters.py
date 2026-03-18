from datetime import datetime

def date_parser(date: str, toString=True):
    if isinstance(date, datetime):
        if toString:
            return str(date.date())
        return date
    
    possible_formats = [
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d %m %Y",
        "%d %B %Y",
        "%d %b %Y"
    ]
    
    for fmt in possible_formats:
        try:
            date_obj = datetime.strptime(date, fmt)
            if toString:
                return date_obj.strftime("%Y-%m-%d")
            else:
                return date_obj
        except ValueError:
            continue
    
    print(f"Warning: Invalid date format -> {date}")
    return None