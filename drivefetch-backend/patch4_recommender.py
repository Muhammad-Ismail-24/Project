import re

with open('agents/recommender.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update UserIntent
content = content.replace(
    'body_style:        Optional[Literal["SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van"]] = None',
    'body_style:        Optional[Literal["SUV", "Mini SUV", "Sedan", "Hatchback", "Pickup", "Crossover", "Van", "MPV"]] = None'
)

# 2. Update extract_intent prompt
old_prompt = (
    "- body_style: 'car' or 'sedan' -> Sedan. 'SUV' or '4x4' -> SUV.\\n\"\n"
    "        \"  'small car' or 'hatchback' -> Hatchback. 'pickup' or 'truck' -> Pickup.\\n\"\n"
    "        \"  'crossover' or 'compact SUV' -> Crossover.\\n\""
)
new_prompt = (
    "- body_style: 'car' or 'sedan' -> Sedan. 'SUV' or '4x4' -> SUV. 'mini suv' or 'compact 4x4' -> Mini SUV.\\n\"\n"
    "        \"  'small car' or 'hatchback' -> Hatchback. 'pickup' or 'truck' -> Pickup.\\n\"\n"
    "        \"  'crossover' -> Crossover. 'van' -> Van. 'mpv' or '11 seater' -> MPV.\\n\""
)
content = content.replace(old_prompt, new_prompt)

# 3. Add new vehicles
mitsubishi_mini_pajero = '\n    "mitsubishi:mini pajero": {"lo": 800_000, "hi": 2_500_000, "styles": {"Mini SUV", "SUV"}, "drive": "4x4", "transmission": "both", "tags": {"offroad", "city", "economy"}, "chinese": False},'
content = re.sub(r'("mitsubishi:pajero":\s*\{.*?\n)', r'\g<1>' + mitsubishi_mini_pajero + '\n', content)

hyundai_santa_fe = '\n    "hyundai:santa fe": {"lo": 12_000_000, "hi": 20_000_000, "styles": {"SUV", "Crossover"}, "drive": "AWD", "transmission": "auto", "tags": {"family", "luxury", "7seat"}, "chinese": False},'
content = re.sub(r'("hyundai:palisade":\s*\{.*?\n)', r'\g<1>' + hyundai_santa_fe + '\n', content)

# 4. Update existing styles
def replace_styles(model, new_styles):
    global content
    # Use regex to find the model and replace its styles set
    # \"model\": \s* {\"lo\": ..., \"hi\": ..., \"styles\": \{.*?\}
    pattern = r'("' + re.escape(model) + r'":\s*\{.*?)"styles":\s*\{[^}]*\}'
    content = re.sub(pattern, r'\1"styles": ' + new_styles, content)

replace_styles("kia:carnival", '{"Van", "MPV"}')
replace_styles("suzuki:jimny", '{"Crossover", "Mini SUV"}')
replace_styles("daihatsu:terios", '{"Crossover", "Mini SUV"}')
replace_styles("daihatsu:rocky", '{"Crossover", "Mini SUV", "Hatchback"}')
replace_styles("toyota:raize", '{"Crossover", "Hatchback"}')
replace_styles("toyota:yaris cross", '{"Crossover", "Hatchback"}')
replace_styles("toyota:rush", '{"SUV", "Hatchback", "MPV"}')

with open('agents/recommender.py', 'w', encoding='utf-8') as f:
    f.write(content)
