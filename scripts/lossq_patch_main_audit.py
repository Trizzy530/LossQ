from pathlib import Path
import re

main_path = Path("backend/app/main.py")

if not main_path.exists():
    raise SystemExit("backend/app/main.py not found. Run this from C:\\Users\\tmcke\\lossq")

text = main_path.read_text(encoding="utf-8")

if "from app.models.audit_log import AuditLog" not in text:
    marker = "from app.models.account_profile import AccountProfile"
    if marker in text:
        text = text.replace(marker, marker + "\nfrom app.models.audit_log import AuditLog")
    else:
        text += "\nfrom app.models.audit_log import AuditLog\n"

if "audit_logs" not in text:
    routes_match = re.search(r"from app\.routes import \((.*?)\)", text, flags=re.S)
    if routes_match:
        inner = routes_match.group(1)
        if "audit_logs" not in inner:
            inner = inner.rstrip()
            if inner.endswith(","):
                inner = inner + "\n    audit_logs,"
            else:
                inner = inner + ",\n    audit_logs,"
            text = text[:routes_match.start(1)] + inner + text[routes_match.end(1):]
    else:
        text = text.replace("from app.routes import", "from app.routes import audit_logs,")
        if "from app.routes import audit_logs" not in text:
            text += "\nfrom app.routes import audit_logs\n"

if "app.include_router(audit_logs.router)" not in text:
    include_lines = [m for m in re.finditer(r"app\.include_router\([^)]+\)", text)]
    if include_lines:
        last = include_lines[-1]
        text = text[:last.end()] + "\napp.include_router(audit_logs.router)" + text[last.end():]
    else:
        text += "\napp.include_router(audit_logs.router)\n"

main_path.write_text(text, encoding="utf-8")
print("Patched backend/app/main.py for audit_logs route.")
