
from pathlib import Path
import re

main_path = Path("backend/app/main.py")

if not main_path.exists():
    raise SystemExit("backend/app/main.py not found. Run this from C:\\Users\\tmcke\\lossq")

text = main_path.read_text(encoding="utf-8")

fastapi_import = re.search(r"from fastapi import ([^\n]+)", text)
if fastapi_import:
    imports = [item.strip() for item in fastapi_import.group(1).split(",")]
    changed = False
    for needed in ["Request", "Response"]:
        if needed not in imports:
            imports.append(needed)
            changed = True
    if changed:
        text = text[:fastapi_import.start(1)] + ", ".join(imports) + text[fastapi_import.end(1):]
else:
    text = "from fastapi import Request, Response\n" + text

if "from fastapi.middleware.cors import CORSMiddleware" not in text:
    text = "from fastapi.middleware.cors import CORSMiddleware\n" + text

route_block = re.search(r"from app\.routes import \((.*?)\)", text, flags=re.S)
if route_block:
    inner = route_block.group(1)
    if "audit_logs" not in inner:
        inner = inner.rstrip()
        inner = inner + ("\n    audit_logs," if inner.endswith(",") else ",\n    audit_logs,")
        text = text[:route_block.start(1)] + inner + text[route_block.end(1):]
elif "from app.routes import audit_logs" not in text:
    text += "\nfrom app.routes import audit_logs\n"

if "from app.models.audit_log import AuditLog" not in text:
    text += "\nfrom app.models.audit_log import AuditLog\n"

standard_cors = (
    "\napp.add_middleware(\n"
    "    CORSMiddleware,\n"
    "    allow_origins=[\n"
    "        \"https://lossq.com\",\n"
    "        \"https://www.lossq.com\",\n"
    "        \"http://localhost:3000\",\n"
    "        \"http://127.0.0.1:3000\",\n"
    "    ],\n"
    "    allow_origin_regex=r\"https://.*\\\\.vercel\\\\.app\",\n"
    "    allow_credentials=True,\n"
    "    allow_methods=[\"*\"],\n"
    "    allow_headers=[\"*\"],\n"
    ")\n"
)

if "app.add_middleware(" not in text or "CORSMiddleware" not in text[text.find("app.add_middleware("):text.find("app.add_middleware(")+700]:
    app_match = re.search(r"app\s*=\s*FastAPI\([^\n]*\)\s*", text)
    if app_match:
        text = text[:app_match.end()] + standard_cors + text[app_match.end():]
    else:
        text += standard_cors

hard_marker = "def lossq_emergency_cors_headers"
hard_cors = (
    "\nALLOWED_LOSSQ_ORIGINS = {\n"
    "    \"https://lossq.com\",\n"
    "    \"https://www.lossq.com\",\n"
    "    \"http://localhost:3000\",\n"
    "    \"http://127.0.0.1:3000\",\n"
    "}\n\n"
    "def lossq_emergency_cors_headers(origin: str | None) -> dict:\n"
    "    if not origin:\n"
    "        return {}\n"
    "    allowed = origin in ALLOWED_LOSSQ_ORIGINS or (origin.startswith(\"https://\") and origin.endswith(\".vercel.app\"))\n"
    "    if not allowed:\n"
    "        return {}\n"
    "    return {\n"
    "        \"Access-Control-Allow-Origin\": origin,\n"
    "        \"Vary\": \"Origin\",\n"
    "        \"Access-Control-Allow-Credentials\": \"true\",\n"
    "        \"Access-Control-Allow-Methods\": \"GET, POST, PUT, PATCH, DELETE, OPTIONS\",\n"
    "        \"Access-Control-Allow-Headers\": \"Authorization, Content-Type, Accept, Origin, X-Requested-With\",\n"
    "        \"Access-Control-Max-Age\": \"86400\",\n"
    "    }\n\n"
    "@app.middleware(\"http\")\n"
    "async def lossq_emergency_cors_middleware(request: Request, call_next):\n"
    "    origin = request.headers.get(\"origin\")\n"
    "    headers = lossq_emergency_cors_headers(origin)\n"
    "    if request.method == \"OPTIONS\":\n"
    "        return Response(status_code=200, headers=headers)\n"
    "    try:\n"
    "        response = await call_next(request)\n"
    "    except Exception as exc:\n"
    "        response = Response(content=f'{{\"detail\":\"Internal server error\",\"error\":\"{str(exc)}\"}}', status_code=500, media_type=\"application/json\")\n"
    "    for key, value in headers.items():\n"
    "        response.headers[key] = value\n"
    "    return response\n"
)

if hard_marker not in text:
    app_match = re.search(r"app\s*=\s*FastAPI\([^\n]*\)\s*", text)
    if app_match:
        text = text[:app_match.end()] + hard_cors + text[app_match.end():]
    else:
        text += hard_cors

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
print("Emergency hard CORS middleware added to backend/app/main.py")
