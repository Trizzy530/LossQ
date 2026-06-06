from pathlib import Path
import re

main_path = Path("backend/app/main.py")
if not main_path.exists():
    raise SystemExit("backend/app/main.py not found. Run from C:\\Users\\tmcke\\lossq")

text = main_path.read_text(encoding="utf-8")

if "from fastapi.middleware.cors import CORSMiddleware" not in text:
    if "from fastapi import" in text:
        text = re.sub(r"(from fastapi import[^\n]*\n)", r"\1from fastapi.middleware.cors import CORSMiddleware\n", text, count=1)
    else:
        text = "from fastapi.middleware.cors import CORSMiddleware\n" + text

if "from app.models.audit_log import AuditLog" not in text:
    marker = "from app.models.account_profile import AccountProfile"
    if marker in text:
        text = text.replace(marker, marker + "\nfrom app.models.audit_log import AuditLog")
    else:
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

cors_block = """
# Production CORS - must stay before route registration.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lossq.com",
        "https://www.lossq.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\\\\.vercel\\\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

pattern = re.compile(r"\napp\.add_middleware\(\s*CORSMiddleware\s*,.*?\n\)\s*", flags=re.S)
if pattern.search(text):
    text = pattern.sub("\n" + cors_block + "\n", text, count=1)
else:
    m = re.search(r"app\s*=\s*FastAPI\([^\n]*\)\s*", text)
    if m:
        text = text[:m.end()] + "\n" + cors_block + text[m.end():]
    else:
        text += "\n" + cors_block + "\n"

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
print("Patched main.py with audit routes and production CORS.")
