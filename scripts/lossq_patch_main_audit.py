from pathlib import Path
import re

main_path = Path("backend/app/main.py")

if not main_path.exists():
    raise SystemExit("backend/app/main.py not found. Run this from C:\\Users\\tmcke\\lossq")

text = main_path.read_text(encoding="utf-8")

# Add model import so Base.metadata.create_all creates the table.
if "from app.models.audit_log import AuditLog" not in text:
    account_model_marker = "from app.models.account_profile import AccountProfile"
    if account_model_marker in text:
        text = text.replace(account_model_marker, account_model_marker + "\nfrom app.models.audit_log import AuditLog")
    else:
        text += "\nfrom app.models.audit_log import AuditLog\n"

# Ensure audit_logs is imported from app.routes.
if "audit_logs" not in re.sub(r"#.*", "", text):
    route_block = re.search(r"from app\.routes import \((.*?)\)", text, flags=re.S)
    if route_block:
        inner = route_block.group(1)
        if "audit_logs" not in inner:
            stripped = inner.rstrip()
            if stripped.endswith(","):
                stripped += "\n    audit_logs,"
            else:
                stripped += ",\n    audit_logs,"
            text = text[:route_block.start(1)] + stripped + text[route_block.end(1):]
    elif "from app.routes import " in text:
        text = text.replace("from app.routes import ", "from app.routes import audit_logs, ", 1)
    else:
        text += "\nfrom app.routes import audit_logs\n"
elif "from app.routes import" not in text and "audit_logs" not in text:
    text += "\nfrom app.routes import audit_logs\n"

# If the prior condition did not add audit_logs because the word existed in comments/version,
# do a direct safe check against route import block.
if "from app.routes import audit_logs" not in text and "audit_logs," not in text:
    route_block = re.search(r"from app\.routes import \((.*?)\)", text, flags=re.S)
    if route_block:
        inner = route_block.group(1)
        inner = inner.rstrip()
        if inner.endswith(","):
            inner += "\n    audit_logs,"
        else:
            inner += ",\n    audit_logs,"
        text = text[:route_block.start(1)] + inner + text[route_block.end(1):]
    else:
        text += "\nfrom app.routes import audit_logs\n"

# Include both routers.
if "app.include_router(audit_logs.router)" not in text:
    include_matches = list(re.finditer(r"app\.include_router\([^)]+\)", text))
    if include_matches:
        last = include_matches[-1]
        text = text[:last.end()] + "\napp.include_router(audit_logs.router)" + text[last.end():]
    else:
        text += "\napp.include_router(audit_logs.router)\n"

if "app.include_router(audit_logs.compat_router)" not in text:
    anchor = "app.include_router(audit_logs.router)"
    if anchor in text:
        text = text.replace(anchor, anchor + "\napp.include_router(audit_logs.compat_router)", 1)
    else:
        text += "\napp.include_router(audit_logs.compat_router)\n"

main_path.write_text(text, encoding="utf-8")
print("Patched backend/app/main.py with audit log routers.")
