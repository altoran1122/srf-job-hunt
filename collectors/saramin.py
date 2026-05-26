from __future__ import annotations

from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .curation import (
    curate_job,
    is_entry_or_intern,
    is_finance_relevant,
    looks_senior,
)


SARAMIN_URL = "https://oapi.saramin.co.kr/job-search"
USER_AGENT = "SRF-Job-Hunt/0.2 (+personal curation board)"


def _fetch(access_key: str, keyword: str, count: int) -> dict:
    params = {
        "access-key": access_key,
        "keywords": keyword,
        "fields": "posting-date expiration-date keyword-code count",
        "count": count,
        "sort": "pd",
    }
    request = Request(
        f"{SARAMIN_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _nested_text(value, *keys: str) -> str:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    if isinstance(current, dict):
        return str(current.get("name") or "")
    return str(current or "")


def _iso_date(value: str | int | None) -> str:
    if not value:
        return ""
    text = str(value)
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text)).date().isoformat()
        except (ValueError, OSError):
            return ""
    if "T" in text:
        return text.split("T", 1)[0]
    return text[:10]


def _job_items(payload: dict) -> list[dict]:
    jobs = payload.get("jobs", {}).get("job", [])
    if isinstance(jobs, dict):
        return [jobs]
    if isinstance(jobs, list):
        return jobs
    return []


def _to_job(item: dict) -> dict | None:
    position = item.get("position") or {}
    company = _nested_text(item, "company", "detail", "name")
    title = str(position.get("title") or "").strip()
    industry = _nested_text(position, "industry")
    job_code = _nested_text(position, "job-code")
    job_mid = _nested_text(position, "job-mid-code")
    location = _nested_text(position, "location") or "확인 필요"
    job_type = _nested_text(position, "job-type")
    experience = _nested_text(position, "experience-level")
    keyword = str(item.get("keyword") or "")
    source_url = str(item.get("url") or "")
    description_parts = [industry, job_code, job_mid, job_type, experience, keyword]

    if not title or not company or str(item.get("active", "1")) == "0":
        return None
    if looks_senior(title, experience) and not is_entry_or_intern(title, experience):
        return None
    if not is_entry_or_intern(title, experience, job_type, keyword):
        return None
    if not is_finance_relevant(title, company, industry, job_code, job_mid, keyword):
        return None

    close_type = _nested_text(item, "close-type")
    deadline = _iso_date(item.get("expiration-date") or item.get("expiration-timestamp"))
    if close_type in {"채용시", "상시", "수시"}:
        deadline = close_type

    job = {
        "id": f"saramin-{item.get('id')}",
        "title": title,
        "company": company,
        "source": "Saramin",
        "source_url": source_url,
        "apply_url": source_url,
        "level": "entry" if "신입" in experience else "",
        "employment_type": job_type or "확인 필요",
        "location": location,
        "deadline": deadline,
        "published_at": _iso_date(item.get("posting-date") or item.get("posting-timestamp")),
        "description": " ".join(description_parts),
        "status": "new",
        "featured": False,
        "hidden": False,
        "note": "",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return curate_job(job)


def collect_saramin_jobs(access_key: str, keywords: list[str], count: int = 30) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for keyword in keywords:
        payload = _fetch(access_key, keyword, count)
        if "code" in payload and "message" in payload:
            raise RuntimeError(str(payload["message"]))
        for item in _job_items(payload):
            job = _to_job(item)
            if not job or job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)
    return jobs
