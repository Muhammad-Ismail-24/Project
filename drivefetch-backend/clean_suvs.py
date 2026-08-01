import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

strict_suv_list = [
    'toyota:fortuner', 'toyota:prado', 'toyota:land cruiser', 'mitsubishi:pajero',
    'mitsubishi:pajero sport', 'nissan:patrol', 'gwm:tank 500', 'land rover:defender',
    'land rover:discovery', 'land rover:range rover', 'land rover:vogue',
    'land rover:range rover sport', 'lexus:lx570', 'lexus:lx', 'lexus:lx600',
    'bmw:x7', 'mercedes-benz:gls'
]

current_model = None

for i, line in enumerate(lines):
    # Detect if we are starting a new model definition
    # "make:model": {"lo": ...
    match = re.search(r'^\s*"([^"]+)":', line)
    if match:
        current_model = match.group(1)
    
    if current_model and current_model not in strict_suv_list:
        if '"styles":' in line and '"SUV"' in line:
            # Replace "SUV" with "Crossover"
            new_line = line.replace('"SUV"', '"Crossover"')
            
            # Clean up duplicates e.g. {"Crossover", "Crossover"} -> {"Crossover"}
            styles_match = re.search(r'"styles":\s*(\{.*?\})', new_line)
            if styles_match:
                styles_str = styles_match.group(1)
                items = set(re.findall(r'["\']([^"\']+)["\']', styles_str))
                cleaned = "{" + ", ".join(f'"{x}"' for x in items) + "}"
                new_line = new_line.replace(styles_str, cleaned)
            lines[i] = new_line
        
        elif '"styles":' in line and "'SUV'" in line:
            new_line = line.replace("'SUV'", "'Crossover'")
            styles_match = re.search(r'"styles":\s*(\{.*?\})', new_line)
            if styles_match:
                styles_str = styles_match.group(1)
                items = set(re.findall(r'["\']([^"\']+)["\']', styles_str))
                cleaned = "{" + ", ".join(f'"{x}"' for x in items) + "}"
                new_line = new_line.replace(styles_str, cleaned)
            lines[i] = new_line

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
