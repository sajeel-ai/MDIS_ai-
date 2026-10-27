"""Fix entity_contract.py by adding CONDITIONAL to Assertion enum."""
import re

path = "app/schemas/entity_contract.py"
content = open(path, "rb").read().decode("utf-8")

# Remove the botched backtick line if it exists
content = re.sub(r"\r?\n    DISCONTINUED = ['\"]discontinued['\"]`r`n    CONDITIONAL = ['\"]conditional['\"]`r`n", 
                 '\r\n    DISCONTINUED = "discontinued"', content)

# Ensure CONDITIONAL is there
if 'CONDITIONAL = "conditional"' not in content:
    content = content.replace(
        'DISCONTINUED = "discontinued"',
        'DISCONTINUED = "discontinued"\r\n    CONDITIONAL = "conditional"'
    )

open(path, "wb").write(content.encode("utf-8"))
print("Done. Checking result:")
for i, line in enumerate(content.splitlines(), 1):
    if "DISCONTINUED" in line or "CONDITIONAL" in line:
        print(f"  line {i}: {line!r}")

