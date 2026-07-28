import re

with open("agents/recommender.py", "r", encoding="utf-8") as f:
    content = f.read()

# Count make occurrences per array block in the few-shot section
fewshot_start = content.find("FEW-SHOT")
fewshot_content = content[fewshot_start:]
blocks = re.findall(r'\[[\s\S]*?\]', fewshot_content)
for i, b in enumerate(blocks):
    c = b.count('"make"')
    if c > 0:
        print(f"Array {i+1}: {c} objects")

# Verify key phrases
checks = [
    ("EXACTLY 3 tier-1", "EXACTLY 3 tier-1" in content),
    ("Q-DOMINANCE present", "Q-DOMINANCE" in content),
    ("Q7 DIVERSITY removed", "Q7. DIVERSITY" not in content),
    ("Q-QUOTA removed", "Q-QUOTA" not in content),
    ("UP TO 5 removed from contract", "UP TO 5 objects" not in content),
    ("EXACTLY 3 objects in contract", "EXACTLY 3 objects" in content),
    ("Fallback max 3", "max 3" in content),
]
print()
for label, ok in checks:
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {label}")

# Verify syntax
import py_compile
try:
    py_compile.compile("agents/recommender.py", doraise=True)
    print("\n  [OK] agents/recommender.py compiles")
except py_compile.PyCompileError as e:
    print(f"\n  [FAIL] agents/recommender.py: {e}")

try:
    py_compile.compile("api/recommend_routes.py", doraise=True)
    print("  [OK] api/recommend_routes.py compiles")
except py_compile.PyCompileError as e:
    print(f"  [FAIL] api/recommend_routes.py: {e}")
