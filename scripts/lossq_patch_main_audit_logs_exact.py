from pathlib import Path
import re

main_path = Path("backend/app/main.py")

if not main_path.exists():
    raise SystemExit("backend/app/main.py not found. Run this from C:\\Users\\tmcke\\lossq")

text = main_path.read_text(encoding="utf-8")

if "from app.models.audit_log import AuditLog" not in text:
    text += "\nfrom app.models.audit_log import AuditLog\n"

route_block = re.search(r"from app\.routes import \((.*?)\)", text, flags=re.S)

if route_block:
    inner = route_block.group(1)
    if "audit_logs" not in inner:
        inner = inner.rstrip()
        inner = inner + ("\n    audit_logs," if inner.endswith(",") else ",\n    audit_logs,")
        text = text[:route_block.start(1)] + inner + text[route_block.end(1):]
elif "from app.routes import audit_logs" not in text:
    text += "\nfrom app.routes import audit_logs\n"

if "app.include_router(audit_logs.router)" not in text:
    matches = list(re.finditer(r"app\.include_router\([^)]+\)", text))
    if matches:
        last = matches[-1]
        text = text[:last.end()] + "\napp.include_router(audit_logs.router)" + text[last.end():]
    else:
        text += "\napp.include_router(audit_logs.router)\n"

if "app.include_router(audit_logs.compat_router)" not in text:
    text = text.replace(
        "app.include_router(audit_logs.router)",
        "app.include_router(audit_logs.router)\napp.include_router(audit_logs.compat_router)",
        1,
    )

main_path.write_text(text, encoding="utf-8")
print("Patched main.py to include /audit-logs and compatibility audit routes.")
