import json
import re

def parse_partial_json(json_str: str) -> dict:
    """
    Attempts to parse a potentially incomplete JSON string from an LLM stream.
    Returns a valid dict as close to the intended structure as possible.
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
        
    # Heuristic: Find the last complete block by matching braces.
    # We know the structure is roughly {"title": "...", "template_type": "...", "blocks": [ ... ]}
    
    # Try to close strings and arrays
    # 1. Close open strings
    # 2. Close open arrays/objects
    
    # A simple but highly effective trick for streaming LLM JSON:
    # Just find the last complete block and construct a valid JSON out of it.
    
    blocks = []
    
    # Try to extract the title
    title_match = re.search(r'"title"\s*:\s*"([^"]+)"', json_str)
    title = title_match.group(1) if title_match else ""
    
    # Extract fully formed block objects. 
    # We look for {"type": ...} that have balanced braces.
    
    brace_level = 0
    in_string = False
    escape = False
    
    current_block_start = -1
    
    for i, char in enumerate(json_str):
        if escape:
            escape = False
            continue
            
        if char == '\\':
            escape = True
            continue
            
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                if brace_level == 0:
                    # Potential start of a block
                    # But we only want blocks inside the "blocks" array. 
                    # We'll just capture all top-level-ish braces that contain "type"
                    current_block_start = i
                brace_level += 1
            elif char == '}':
                brace_level -= 1
                if brace_level == 0 and current_block_start != -1:
                    block_str = json_str[current_block_start:i+1]
                    if '"type"' in block_str:
                        try:
                            block_obj = json.loads(block_str)
                            blocks.append(block_obj)
                        except json.JSONDecodeError:
                            pass
                    current_block_start = -1
                    
    return {
        "title": title,
        "blocks": blocks,
        "recommended_actions": []
    }
