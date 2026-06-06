from pathlib import Path
import re

upload_path = Path("backend/app/routes/upload.py")

if not upload_path.exists():
    raise SystemExit("backend/app/routes/upload.py not found. Run this from C:\\Users\\tmcke\\lossq")

text = upload_path.read_text(encoding="utf-8")

# Import safe audit writer. If upload.py does not use it directly yet, this is harmless.
if "from app.services.audit_service import write_audit_event" not in text:
    # Add near other app imports.
    insert_after = "from app.services.loss_run_pipeline import parse_loss_run_file"
    if insert_after in text:
        text = text.replace(insert_after, insert_after + "\nfrom app.services.audit_service import write_audit_event")
    else:
        text = "from app.services.audit_service import write_audit_event\n" + text

# Add a helper that upload.py can call without breaking if not used.
helper = 