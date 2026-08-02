import os
import re

def replace_in_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    # Replace variations
    new_content = re.sub(r'Drive Fetch', 'Drive Fetch', content)
    new_content = re.sub(r'drivefetch', 'drivefetch', new_content)
    new_content = re.sub(r'Drive Fetch', 'Drive Fetch', new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated: {filepath}")

def main():
    base_dir = r"D:\Old Assignments and Projects\CarFinder System\DriveFetch\drivefetch-frontend"
    for root, dirs, files in os.walk(base_dir):
        if "node_modules" in root or ".git" in root:
            continue
        for file in files:
            if file.endswith(('.py', '.md', '.ts', '.tsx', '.html', '.json')):
                replace_in_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
