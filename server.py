from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from collectors.curation import curate_job, is_finance_role_relevant, is_non_finance_role, slugify


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
REPO_DATA_DIR = ROOT / "data"
DATA_DIR = Path(os.environ.get("SRF_DATA_DIR", str(REPO_DATA_DIR))).resolve()
DATA_FILE = DATA_DIR / "jobs.json"
USERS_FILE = DATA_DIR / "users.json"
CONFIG_FILE = DATA_DIR / "config.json"
SEED_JOBS_FILE = REPO_DATA_DIR / "jobs.json"
DEFAULT_PASSWORD = "srf2026"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14
KOFIA_REFRESH_SECONDS = 60 * 60
RECOMMENDATION_THRESHOLD = 5
JOB_MAX_AGE_DAYS = 90
ROLLING_DEADLINES = {"상시", "수시", "채용시"}
DEFAULT_KOFIA_PAGES = 10
DATA_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, fallback):
    with DATA_LOCK:
        if not path.exists():
            return fallback
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)


def save_json(path: Path, payload) -> None:
    with DATA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copyfile(path, path.with_suffix(".backup.json"))
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() and SEED_JOBS_FILE.exists() and SEED_JOBS_FILE.resolve() != DATA_FILE.resolve():
        shutil.copyfile(SEED_JOBS_FILE, DATA_FILE)
    if not USERS_FILE.exists():
        save_json(USERS_FILE, {"users": {}})


def hash_password(password: str, salt: str | None = None) -> dict:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000)
    return {"salt": salt, "hash": digest.hex()}


def check_password(password: str, password_config: dict) -> bool:
    salt = password_config.get("salt", "")
    expected = password_config.get("hash", "")
    if not salt or not expected:
        return False
    actual = hash_password(password, salt=salt)["hash"]
    return hmac.compare_digest(actual, expected)


def ensure_config() -> dict:
    config = load_json(CONFIG_FILE, None)
    if config:
        return config
    initial_password = os.environ.get("SRF_PASSWORD", DEFAULT_PASSWORD)
    config = {
        "password": hash_password(initial_password),
        "token_secret": secrets.token_hex(32),
        "saramin_access_key": os.environ.get("SARAMIN_ACCESS_KEY", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    save_json(CONFIG_FILE, config)
    return config


def save_config(config: dict) -> None:
    config["updated_at"] = now_iso()
    save_json(CONFIG_FILE, config)


def load_jobs() -> list[dict]:
    return load_json(DATA_FILE, [])


def save_jobs(jobs: list[dict]) -> None:
    save_json(DATA_FILE, jobs)


def load_users() -> dict:
    return load_json(USERS_FILE, {"users": {}})


def save_users(users: dict) -> None:
    save_json(USERS_FILE, users)


def normalize_user_name(value: str) -> str:
    value = " ".join(str(value or "").split())
    if not value:
        return ""
    return slugify(value.lower())[:40]


def ensure_user(display_name: str) -> dict:
    users = load_users()
    user_id = normalize_user_name(display_name)
    if not user_id:
        raise ValueError("이름을 입력해 주세요.")
    user = users["users"].get(user_id)
    if not user:
        user = {
            "id": user_id,
            "display_name": display_name.strip(),
            "jobs": {},
            "notification": default_notification_settings(),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        users["users"][user_id] = user
        save_users(users)
    elif user.get("display_name") != display_name.strip():
        user["display_name"] = display_name.strip()
        user["updated_at"] = now_iso()
        users["users"][user_id] = user
        save_users(users)
    if "notification" not in user:
        user["notification"] = default_notification_settings()
        user["updated_at"] = now_iso()
        users["users"][user_id] = user
        save_users(users)
    return user


def b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def make_token(user_id: str) -> str:
    config = ensure_config()
    payload = json.dumps(
        {"user_id": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    body = b64_encode(payload)
    signature = hmac.new(config["token_secret"].encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{b64_encode(signature)}"


def verify_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        config = ensure_config()
        expected = hmac.new(config["token_secret"].encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64_decode(signature), expected):
            return None
        payload = json.loads(b64_decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        users = load_users()
        return users["users"].get(payload.get("user_id"))
    except Exception:
        return None


def mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def default_user_job_state() -> dict:
    return {"saved": False, "status": "none", "comment": "", "hidden": False}


def default_notification_settings() -> dict:
    return {
        "enabled": False,
        "telegram_chat_id": "",
        "filters": {
            "q": "",
            "levels": [],
            "sources": [],
            "tags": [],
            "deadline_days": 0,
            "featured_only": False,
        },
        "notified_jobs": {},
    }


def listify(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = value.split(",")
    else:
        raw = []
    return [str(item).strip() for item in raw if str(item).strip()]


def sanitize_notification_settings(payload: dict, current: dict | None = None) -> dict:
    settings = {**default_notification_settings(), **(current or {})}
    filters = {**default_notification_settings()["filters"], **(settings.get("filters") or {})}

    if "enabled" in payload:
        settings["enabled"] = bool(payload.get("enabled"))
    if "telegram_chat_id" in payload:
        settings["telegram_chat_id"] = str(payload.get("telegram_chat_id") or "").strip()
    if "filters" in payload:
        incoming = payload.get("filters") or {}
        filters["q"] = str(incoming.get("q") or "").strip()
        filters["levels"] = listify(incoming.get("levels"))
        filters["sources"] = listify(incoming.get("sources"))
        filters["tags"] = listify(incoming.get("tags"))
        try:
            filters["deadline_days"] = max(0, min(90, int(incoming.get("deadline_days") or 0)))
        except (TypeError, ValueError):
            filters["deadline_days"] = 0
        filters["featured_only"] = bool(incoming.get("featured_only"))

    notified_jobs = settings.get("notified_jobs")
    settings["notified_jobs"] = notified_jobs if isinstance(notified_jobs, dict) else {}
    settings["filters"] = filters
    return settings


def merge_user_state(job: dict, user: dict) -> dict:
    merged = dict(job)
    merged["user_state"] = {
        **default_user_job_state(),
        **(user.get("jobs", {}).get(job.get("id"), {}) or {}),
    }
    return merged


def update_user_job(user_id: str, job_id: str, updates: dict) -> dict:
    users = load_users()
    user = users["users"].get(user_id)
    if not user:
        raise KeyError("사용자를 찾지 못했습니다.")
    state = {**default_user_job_state(), **(user.get("jobs", {}).get(job_id, {}) or {})}

    allowed = {"saved", "status", "comment", "hidden"}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if key == "status" and value not in {"none", "watching", "applied"}:
            continue
        state[key] = value

    if state["status"] == "watching":
        state["saved"] = True
    if state["status"] == "none" and not state.get("comment"):
        state["hidden"] = bool(state.get("hidden", False))

    state["updated_at"] = now_iso()
    user.setdefault("jobs", {})[job_id] = state
    user["updated_at"] = now_iso()
    users["users"][user_id] = user
    save_users(users)
    return state


def parse_job_date(value: str | None):
    if not value:
        return None
    value = str(value).strip()
    if not value or value in ROLLING_DEADLINES:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def summary_parts(job: dict) -> list[str]:
    summary = job.get("summary") or {}
    return [
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        str(summary.get("work") or ""),
        str(summary.get("requirements") or ""),
        str(summary.get("advantages") or ""),
        str(summary.get("notice") or ""),
    ]


def is_rolling_job(job: dict) -> bool:
    deadline = str(job.get("deadline") or "").strip()
    if deadline in ROLLING_DEADLINES:
        return True
    text = " ".join(summary_parts(job))
    return any(keyword in text for keyword in ("상시채용", "상시 모집", "채용시", "수시채용"))


def auto_hidden_reason(job: dict) -> str:
    if str(job.get("source") or "") == "Superookie":
        employment = str(job.get("employment_type") or "")
        if "주니어경력" in employment:
            return "슈퍼루키 주니어경력 제외"
        parts = summary_parts(job)
        if is_non_finance_role(*parts):
            return "금융회사 비금융직렬 제외"
        if not is_finance_role_relevant(*parts):
            return "금융직무 관련성 낮음"

    if not is_rolling_job(job):
        base_date = parse_job_date(job.get("published_at")) or parse_job_date(job.get("created_at"))
        if base_date and (datetime.now().astimezone().date() - base_date).days > JOB_MAX_AGE_DAYS:
            return "3개월 지난 공고"
    return ""


def reaction_count_for_job(users: dict, job_id: str | None) -> int:
    if not job_id:
        return 0
    count = 0
    for user in users.get("users", {}).values():
        state = (user.get("jobs", {}) or {}).get(job_id, {}) or {}
        if state.get("saved") or state.get("status") in {"watching", "applied"}:
            count += 1
    return count


def public_job_state(job: dict, users: dict) -> dict:
    public = dict(job)
    public.pop("hidden_reason", None)
    reaction_count = reaction_count_for_job(users, public.get("id"))
    public["reaction_count"] = reaction_count
    public["featured"] = reaction_count >= RECOMMENDATION_THRESHOLD
    reason = auto_hidden_reason(public)
    public["auto_hidden"] = bool(reason)
    if reason:
        public["hidden_reason"] = reason
    return public


def job_payload(job: dict, user: dict, users: dict) -> dict:
    return merge_user_state(public_job_state(job, users), user)


def jobs_payload(jobs: list[dict], user: dict, include_hidden: bool = False) -> list[dict]:
    users = load_users()
    payload = []
    for job in jobs:
        public = public_job_state(job, users)
        if (public.get("hidden") or public.get("auto_hidden")) and not include_hidden:
            continue
        payload.append(merge_user_state(public, user))
    return payload


def days_until_deadline(job: dict) -> int | None:
    deadline = parse_job_date(job.get("deadline"))
    if not deadline:
        return None
    return (deadline - datetime.now().astimezone().date()).days


def job_search_text(job: dict) -> str:
    parts = [
        job.get("company", ""),
        job.get("title", ""),
        job.get("source", ""),
        job.get("location", ""),
        job.get("employment_type", ""),
        " ".join(job.get("tags") or []),
        *summary_parts(job),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def notification_matches(job: dict, filters: dict) -> bool:
    if filters.get("featured_only") and not job.get("featured"):
        return False
    levels = set(listify(filters.get("levels")))
    if levels and str(job.get("level") or "") not in levels:
        return False
    sources = set(listify(filters.get("sources")))
    if sources and str(job.get("source") or "") not in sources:
        return False
    tags = listify(filters.get("tags"))
    if tags and not all(tag in (job.get("tags") or []) for tag in tags):
        return False
    deadline_days = int(filters.get("deadline_days") or 0)
    if deadline_days:
        left = days_until_deadline(job)
        if left is None or left < 0 or left > deadline_days:
            return False
    query = str(filters.get("q") or "").strip().lower()
    if query and query not in job_search_text(job):
        return False
    return True


def telegram_message(job: dict) -> str:
    tags = ", ".join(job.get("tags") or [])
    deadline = job.get("deadline") or "마감 확인"
    link = job.get("apply_url") or job.get("source_url") or ""
    lines = [
        "[SRF 새 공고]",
        f"{job.get('company', '회사 확인')}",
        f"{job.get('title', '공고명 확인')}",
        f"구분: {job.get('employment_type') or job.get('level') or '확인 필요'}",
        f"마감: {deadline}",
    ]
    if tags:
        lines.append(f"태그: {tags}")
    if link:
        lines.append(f"링크: {link}")
    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        body = json.loads(response.read().decode("utf-8"))
        if not body.get("ok"):
            raise RuntimeError(body.get("description") or "Telegram sendMessage failed")


def latest_telegram_chat(token: str) -> dict:
    request = Request(f"https://api.telegram.org/bot{token}/getUpdates", method="GET")
    with urlopen(request, timeout=15) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or "Telegram getUpdates failed")
    for update in reversed(body.get("result") or []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if chat.get("id"):
            name = " ".join(
                str(part)
                for part in (chat.get("first_name"), chat.get("last_name"), chat.get("username"))
                if part
            ).strip()
            return {"chat_id": str(chat["id"]), "name": name, "type": chat.get("type", "")}
    raise RuntimeError("최근 텔레그램 대화를 찾지 못했습니다. 봇에게 /start를 먼저 보내 주세요.")


def notify_matching_users(new_jobs: list[dict]) -> dict:
    config = ensure_config()
    token = str(config.get("telegram_bot_token") or "").strip()
    if not token or not new_jobs:
        return {"sent": 0, "skipped": True}

    users = load_users()
    sent = 0
    errors: list[str] = []
    changed = False

    for raw_job in new_jobs:
        job = public_job_state(raw_job, users)
        if job.get("hidden") or job.get("auto_hidden"):
            continue
        job_id = job.get("id")
        if not job_id:
            continue
        for user_id, user in users.get("users", {}).items():
            settings = sanitize_notification_settings({}, user.get("notification") or {})
            if not settings.get("enabled") or not settings.get("telegram_chat_id"):
                continue
            if job_id in (settings.get("notified_jobs") or {}):
                continue
            if not notification_matches(job, settings.get("filters") or {}):
                continue
            try:
                send_telegram_message(token, settings["telegram_chat_id"], telegram_message(job))
            except Exception as exc:
                errors.append(f"{user_id}:{job_id}:{exc}")
                continue
            settings.setdefault("notified_jobs", {})[job_id] = now_iso()
            user["notification"] = settings
            user["updated_at"] = now_iso()
            sent += 1
            changed = True

    if changed:
        save_users(users)
    return {"sent": sent, "errors": errors, "skipped": False}


def merge_jobs(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, list[dict]]:
    by_key: dict[str, dict] = {}
    order: list[str] = []

    def key_for(job: dict) -> str:
        if job.get("is_sample") and job.get("id"):
            return f"id:{job['id']}"
        source_url = job.get("source_url") or job.get("apply_url")
        if source_url:
            return f"url:{source_url}"
        if job.get("id"):
            return f"id:{job['id']}"
        return f"title:{job.get('company', '')}:{job.get('title', '')}".lower()

    for job in existing:
        key = key_for(job)
        if key in by_key:
            continue
        by_key[key] = job
        order.append(key)

    added = 0
    added_jobs: list[dict] = []
    for raw in incoming:
        job = curate_job(raw)
        key = key_for(job)
        if key in by_key:
            current = by_key[key]
            preserved = {
                "featured": current.get("featured", False),
                "hidden": current.get("hidden", False),
                "note": current.get("note", ""),
                "created_at": current.get("created_at", now_iso()),
                "is_sample": current.get("is_sample", False),
            }
            current.update(job)
            current.update(preserved)
            current["updated_at"] = now_iso()
        else:
            job.setdefault("id", slugify(f"{job.get('source', 'job')}-{job.get('company', '')}-{job.get('title', '')}"))
            job.setdefault("featured", False)
            job.setdefault("hidden", False)
            job.setdefault("note", "")
            job.setdefault("created_at", now_iso())
            job["updated_at"] = now_iso()
            by_key[key] = job
            order.append(key)
            added += 1
            added_jobs.append(job)

    return [by_key[key] for key in order], added, added_jobs


def import_kofia_once(max_pages: int = DEFAULT_KOFIA_PAGES) -> dict:
    from collectors.kofia import collect_kofia_jobs

    imported = collect_kofia_jobs(max_pages=max(1, min(max_pages, 30)), fetch_details=True)
    jobs, added, added_jobs = merge_jobs(load_jobs(), imported)
    save_jobs(jobs)
    notification = notify_matching_users(added_jobs)
    return {"imported": len(imported), "added": added, "jobs": jobs, "notification": notification}


def import_saramin_once(access_key: str | None = None, count: int = 30) -> dict:
    from collectors.saramin import collect_saramin_jobs

    config = ensure_config()
    key = access_key or config.get("saramin_access_key", "")
    if not key:
        return {"imported": 0, "added": 0, "jobs": load_jobs(), "skipped": True}
    imported = collect_saramin_jobs(
        access_key=key,
        keywords=["금융 인턴", "금융 신입", "증권 인턴", "자산운용 인턴"],
        count=max(1, min(count, 100)),
    )
    jobs, added, added_jobs = merge_jobs(load_jobs(), imported)
    save_jobs(jobs)
    notification = notify_matching_users(added_jobs)
    return {"imported": len(imported), "added": added, "jobs": jobs, "skipped": False, "notification": notification}


def import_superookie_once(pages_per_keyword: int = 2) -> dict:
    from collectors.superookie import collect_superookie_jobs

    imported = collect_superookie_jobs(pages_per_keyword=max(1, min(pages_per_keyword, 5)))
    jobs, added, added_jobs = merge_jobs(load_jobs(), imported)
    save_jobs(jobs)
    notification = notify_matching_users(added_jobs)
    return {"imported": len(imported), "added": added, "jobs": jobs, "notification": notification}


def start_auto_import_scheduler() -> None:
    def worker() -> None:
        while True:
            try:
                kofia = import_kofia_once(max_pages=DEFAULT_KOFIA_PAGES)
                print(
                    f"[{now_iso()}] KOFIA auto import checked {kofia['imported']} jobs, added {kofia['added']}, notified {kofia.get('notification', {}).get('sent', 0)}",
                    flush=True,
                )
            except Exception as exc:
                print(f"[{now_iso()}] KOFIA auto import failed: {exc}", flush=True)
            try:
                saramin = import_saramin_once(count=30)
                if not saramin.get("skipped"):
                    print(
                        f"[{now_iso()}] Saramin auto import checked {saramin['imported']} jobs, added {saramin['added']}, notified {saramin.get('notification', {}).get('sent', 0)}",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[{now_iso()}] Saramin auto import failed: {exc}", flush=True)
            try:
                superookie = import_superookie_once(pages_per_keyword=2)
                print(
                    f"[{now_iso()}] Superookie auto import checked {superookie['imported']} jobs, added {superookie['added']}, notified {superookie.get('notification', {}).get('sent', 0)}",
                    flush=True,
                )
            except Exception as exc:
                print(f"[{now_iso()}] Superookie auto import failed: {exc}", flush=True)
            time.sleep(KOFIA_REFRESH_SECONDS)

    threading.Thread(target=worker, name="kofia-auto-import", daemon=True).start()


class SRFHandler(SimpleHTTPRequestHandler):
    server_version = "SRFJobHunt/0.2"

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        parts = [part for part in parsed.path.split("/") if part and part not in {".", ".."}]
        if not parts:
            parts = ["index.html"]
        return str(WEB_ROOT.joinpath(*parts))

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _auth_user(self) -> dict | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return verify_token(header.removeprefix("Bearer ").strip())

    def _require_auth(self) -> dict | None:
        user = self._auth_user()
        if not user:
            self._send_json({"error": "로그인이 필요합니다."}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if parsed.path == "/api/me":
            user = self._require_auth()
            if not user:
                return
            config = ensure_config()
            self._send_json(
                {
                    "user": {
                        "id": user["id"],
                        "display_name": user["display_name"],
                        "jobs": user.get("jobs", {}),
                        "notification": sanitize_notification_settings({}, user.get("notification") or {}),
                    },
                    "config": {
                        "saramin_configured": bool(config.get("saramin_access_key")),
                        "saramin_key_masked": mask_key(config.get("saramin_access_key", "")),
                        "telegram_configured": bool(config.get("telegram_bot_token")),
                        "telegram_token_masked": mask_key(config.get("telegram_bot_token", "")),
                    },
                }
            )
            return

        if parsed.path == "/api/jobs":
            user = self._require_auth()
            if not user:
                return
            query = parse_qs(parsed.query)
            include_hidden = query.get("include_hidden", ["false"])[0] == "true"
            jobs = jobs_payload(load_jobs(), user, include_hidden=include_hidden)
            self._send_json({"jobs": jobs, "count": len(jobs)})
            return

        return super().do_GET()

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        user = self._require_auth()
        if not user:
            return

        if parsed.path == "/api/config":
            payload = self._read_json()
            config = ensure_config()
            if "saramin_access_key" in payload:
                config["saramin_access_key"] = str(payload.get("saramin_access_key") or "").strip()
            if "telegram_bot_token" in payload:
                config["telegram_bot_token"] = str(payload.get("telegram_bot_token") or "").strip()
            if payload.get("new_password"):
                config["password"] = hash_password(str(payload["new_password"]))
                config["token_secret"] = secrets.token_hex(32)
            save_config(config)
            import_result = None
            import_error = ""
            if payload.get("saramin_access_key"):
                try:
                    import_result = import_saramin_once(access_key=config.get("saramin_access_key", ""), count=30)
                    import_result = {
                        **import_result,
                        "jobs": jobs_payload(import_result.get("jobs", []), user),
                    }
                except Exception as exc:
                    import_error = str(exc)
            self._send_json(
                {
                    "saramin_configured": bool(config.get("saramin_access_key")),
                    "saramin_key_masked": mask_key(config.get("saramin_access_key", "")),
                    "telegram_configured": bool(config.get("telegram_bot_token")),
                    "telegram_token_masked": mask_key(config.get("telegram_bot_token", "")),
                    "password_changed": bool(payload.get("new_password")),
                    "import_result": import_result,
                    "import_error": import_error,
                }
            )
            return

        if parsed.path == "/api/me/notification":
            users = load_users()
            saved_user = users["users"].get(user["id"])
            if not saved_user:
                self._send_json({"error": "사용자를 찾지 못했습니다."}, HTTPStatus.NOT_FOUND)
                return
            saved_user["notification"] = sanitize_notification_settings(
                self._read_json(),
                saved_user.get("notification") or {},
            )
            saved_user["updated_at"] = now_iso()
            users["users"][user["id"]] = saved_user
            save_users(users)
            self._send_json({"notification": saved_user["notification"]})
            return

        user_match = re.fullmatch(r"/api/user/jobs/([^/]+)", parsed.path)
        if user_match:
            job_id = user_match.group(1)
            if not any(job.get("id") == job_id for job in load_jobs()):
                self._send_json({"error": "공고를 찾지 못했습니다."}, HTTPStatus.NOT_FOUND)
                return
            state = update_user_job(user["id"], job_id, self._read_json())
            jobs = load_jobs()
            users = load_users()
            updated_user = users["users"].get(user["id"], user)
            updated_job = next((job for job in jobs if job.get("id") == job_id), None)
            self._send_json(
                {
                    "user_state": state,
                    "job": job_payload(updated_job, updated_user, users) if updated_job else None,
                }
            )
            return

        job_match = re.fullmatch(r"/api/jobs/([^/]+)", parsed.path)
        if job_match:
            job_id = job_match.group(1)
            updates = self._read_json()
            allowed = {"featured", "hidden", "note", "tags", "deadline", "location"}
            jobs = load_jobs()
            for job in jobs:
                if job.get("id") != job_id:
                    continue
                for key, value in updates.items():
                    if key in allowed:
                        job[key] = value
                job["updated_at"] = now_iso()
                save_jobs(jobs)
                users = load_users()
                self._send_json({"job": job_payload(job, user, users)})
                return
            self._send_json({"error": "공고를 찾지 못했습니다."}, HTTPStatus.NOT_FOUND)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/session":
            payload = self._read_json()
            config = ensure_config()
            if not check_password(str(payload.get("password") or ""), config.get("password", {})):
                self._send_json({"error": "비밀번호가 맞지 않습니다."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                user = ensure_user(str(payload.get("display_name") or ""))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                {
                    "token": make_token(user["id"]),
                    "user": {"id": user["id"], "display_name": user["display_name"], "jobs": user.get("jobs", {})},
                },
                HTTPStatus.CREATED,
            )
            return

        user = self._require_auth()
        if not user:
            return

        if parsed.path == "/api/jobs":
            payload = self._read_json()
            job = curate_job(payload)
            job["id"] = job.get("id") or slugify(f"manual-{job.get('company', '')}-{job.get('title', '')}-{now_iso()}")
            job.setdefault("source", "Manual")
            job.setdefault("source_url", job.get("apply_url", ""))
            job.setdefault("apply_url", job.get("source_url", ""))
            job.setdefault("featured", False)
            job.setdefault("hidden", False)
            job.setdefault("note", "")
            job["created_at"] = now_iso()
            job["updated_at"] = now_iso()
            jobs, added, _added_jobs = merge_jobs(load_jobs(), [job])
            save_jobs(jobs)
            users = load_users()
            saved_job = next((item for item in jobs if item.get("id") == job.get("id")), job)
            self._send_json({"job": job_payload(saved_job, user, users), "added": added}, HTTPStatus.CREATED)
            return

        if parsed.path == "/api/telegram/test":
            config = ensure_config()
            token = str(config.get("telegram_bot_token") or "").strip()
            settings = sanitize_notification_settings({}, user.get("notification") or {})
            chat_id = str(settings.get("telegram_chat_id") or "").strip()
            if not token:
                self._send_json({"error": "텔레그램 봇 토큰을 먼저 저장해 주세요."}, HTTPStatus.BAD_REQUEST)
                return
            if not chat_id:
                self._send_json({"error": "내 텔레그램 chat_id를 먼저 저장해 주세요."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                send_telegram_message(token, chat_id, "SRF Jobs 텔레그램 알림 테스트입니다.")
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._send_json({"sent": True})
            return

        if parsed.path == "/api/telegram/latest-chat":
            config = ensure_config()
            token = str(config.get("telegram_bot_token") or "").strip()
            if not token:
                self._send_json({"error": "텔레그램 봇 토큰을 먼저 저장해 주세요."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self._send_json(latest_telegram_chat(token))
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        if parsed.path == "/api/import/kofia":
            query = parse_qs(parsed.query)
            max_pages = int(query.get("pages", [str(DEFAULT_KOFIA_PAGES)])[0])
            try:
                result = import_kofia_once(max_pages=max_pages)
                self._send_json(
                    {
                        "imported": result["imported"],
                        "added": result["added"],
                        "jobs": jobs_payload(result["jobs"], user),
                    }
                )
            except Exception as exc:  # pragma: no cover - surfaced in UI
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        if parsed.path == "/api/import/saramin":
            query = parse_qs(parsed.query)
            count = int(query.get("count", ["30"])[0])
            config = ensure_config()
            access_key = config.get("saramin_access_key", "")
            if not access_key:
                self._send_json({"error": "사람인 access-key를 먼저 저장해 주세요."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = import_saramin_once(access_key=access_key, count=count)
                self._send_json(
                    {
                        "imported": result["imported"],
                        "added": result["added"],
                        "jobs": jobs_payload(result["jobs"], user),
                    }
                )
            except Exception as exc:  # pragma: no cover - surfaced in UI
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        if parsed.path == "/api/import/superookie":
            query = parse_qs(parsed.query)
            pages = int(query.get("pages", ["2"])[0])
            try:
                result = import_superookie_once(pages_per_keyword=pages)
                self._send_json(
                    {
                        "imported": result["imported"],
                        "added": result["added"],
                        "jobs": jobs_payload(result["jobs"], user),
                    }
                )
            except Exception as exc:  # pragma: no cover - surfaced in UI
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    ensure_data_files()
    ensure_config()
    start_auto_import_scheduler()
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1")
    server = ThreadingHTTPServer((host, port), SRFHandler)
    print(f"SRF Job Hunt running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
