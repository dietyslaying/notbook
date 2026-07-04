from interfaces import IASchema, TelegramKeyboard, TelegramButton, TELEGRAM_CAPABILITIES

def build_keyboard(ia_schema: IASchema) -> TelegramKeyboard:
    if not ia_schema or not ia_schema.nav_buttons:
        return TelegramKeyboard(rows=[])
    
    rows = []
    current_row = []
    
    # Sort buttons by tier, lower tier first (primary actions top)
    sorted_buttons = sorted(ia_schema.nav_buttons, key=lambda b: b.tier)
    
    for btn in sorted_buttons:
        current_row.append(TelegramButton(text=btn.label, callback_data=btn.callback_data))
        if len(current_row) >= TELEGRAM_CAPABILITIES.max_buttons_per_row:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        rows.append(current_row)
        
    return TelegramKeyboard(rows=rows)
