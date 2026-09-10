import csv
import re

def is_balanced(s):
    if not s: return True
    stack = []
    for char in s:
        if char == '(':
            stack.append(char)
        elif char == ')':
            if not stack: return False
            stack.pop()
    return len(stack) == 0

files = [
    'dbt/seeds/coicop_override.csv',
    'dbt/seeds/coicop_text_rules.csv',
    'dbt/seeds/coicop_critical_traps.csv'
]

for file_path in files:
    print(f"Checking {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            for i, row in enumerate(reader, 2):
                for j, col in enumerate(row):
                    if not is_balanced(col):
                        print(f"  Unbalanced parentheses in {file_path} line {i}, col {j}: {col}")
    except Exception as e:
        print(f"  Error reading {file_path}: {e}")
