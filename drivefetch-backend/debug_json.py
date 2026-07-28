import json

with open("agents/recommender.py", "r", encoding="utf-8") as f:
    content = f.read()

s = content[content.find("rugged 4x4 chahiye"):]
arr_start = s.find("[")
arr_end = s.find("\n]", arr_start)
arr_text = s[arr_start:arr_end+2]

# Clean up
arr_text = arr_text.replace("\r\n", "\n").replace("\r", "")

try:
    parsed = json.loads(arr_text)
    print(f"Parsed OK: {len(parsed)} objects")
    for c in parsed:
        make = c.get("make", "")
        model = c.get("model", "")
        print(f"  -> {make} {model}")
except json.JSONDecodeError as e:
    print(f"Parse error at pos {e.pos}: {e.msg}")
    context = arr_text[max(0, e.pos-80):e.pos+80]
    print(f"Context: {repr(context)}")
