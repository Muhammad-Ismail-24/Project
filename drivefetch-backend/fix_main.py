with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if "s | %(levelname)s | %(name)s | %(message)s'" in line:
        continue
    if line.strip() == ")":
        continue
    out.append(line)

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(out)
