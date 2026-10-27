"""Fix openai.py to add 'conditional' to assertion enum in JSON schema."""
path = "app/providers/extraction/openai.py"
content = open(path, "rb").read().decode("utf-8")
old = '"enum": ["present", "absent", "possible", "historical", "family", "hypothetical", "discontinued"]'
new = '"enum": ["present", "absent", "possible", "historical", "family", "hypothetical", "discontinued", "conditional"]'
assert old in content, "Pattern not found!"
content = content.replace(old, new, 1)
open(path, "wb").write(content.encode("utf-8"))
print("Done")

