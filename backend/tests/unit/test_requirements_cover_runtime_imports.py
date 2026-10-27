"""Ensure third-party runtime imports are declared in backend requirements."""

import ast
import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
IMPORT_TO_DISTRIBUTION = {
    "argon2": "argon2-cffi",
    "cv2": "opencv-python-headless",
    "fhir": "fhir.resources",
    "fitz": "pymupdf",
    "jwt": "pyjwt",
    "PIL": "pillow",
}
STDLIB_MODULES = set(getattr(__import__("sys"), "stdlib_module_names", ()))


def _declared_distributions() -> set[str]:
    requirements = BACKEND_ROOT / "requirements.txt"
    declared = set()
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "http://", "https://")):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            declared.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return declared


def _runtime_imports() -> set[str]:
    imported = set()
    app_root = BACKEND_ROOT / "app"
    for source in app_root.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".", 1)[0])
    return imported


def test_runtime_third_party_imports_are_declared_in_requirements():
    declared = _declared_distributions()
    missing = []
    for module in sorted(_runtime_imports()):
        if module in STDLIB_MODULES or module == "app":
            continue
        distribution = IMPORT_TO_DISTRIBUTION.get(module, module)
        normalized = re.sub(r"[-_.]+", "-", distribution).lower()
        if normalized not in declared:
            missing.append(f"{module} (distribution: {distribution})")

    assert not missing, (
        "Runtime imports missing from backend/requirements.txt: "
        + ", ".join(missing)
    )
