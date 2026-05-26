from __future__ import annotations

from datetime import datetime
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .curation import curate_job, is_entry_or_intern, looks_senior


SUPEROOKIE_HOME = "https://www.superookie.com"
SUPEROOKIE_JOBS_URL = f"{SUPEROOKIE_HOME}/jobs"
SUPEROOKIE_API_URL = f"{SUPEROOKIE_HOME}/api/jobs/search"
USER_AGENT = "SRF-Job-Hunt/0.2 (+personal curation board)"
DEFAULT_KEYWORDS = ("금융", "증권", "자산운용", "은행", "애널리스트", "IB", "회계법인", "보험")
FINANCE_PATTERNS = (
    r"금융",
    r"증권",
    r"은행",
    r"보험",
    r"자산운용",
    r"운용사",
    r"투자은행",
    r"투자증권",
    r"캐피탈",
    r"외환",
    r"브로커",
    r"회계법인",
    r"감사",
    r"재무",
    r"(증권|투자|금융).{0,10}리서치",
    r"리서치.{0,10}(증권|투자|금융)",
    r"애널리스트",
    r"펀드",
    r"\bIB\b",
    r"\bM&A\b",
    r"\bECM\b",
    r"\bDCM\b",
    r"\bPE\b",
    r"\bVC\b",
    r"\bfintech\b",
    r"\bfinance\b",
    r"\bfinancial\b",
    r"\bbank\b",
    r"\bsecurities\b",
    r"\basset management\b",
    r"\binvestment banking\b",
    r"\bcapital market",
    r"\binsurance\b",
    r"\baccounting\b",
    r"\baudit\b",
    r"\bvaluation\b",
    r"\brisk\b",
)


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _fetch_json(url: str) -> dict:
    return json.loads(_fetch_text(url))


def _access_token() -> str:
    html = _fetch_text(SUPEROOKIE_JOBS_URL)
    match = re.search(r'loadNext\("https://www\.superookie\.com/api/jobs/search",\s*\'([^\']+)\'', html)
    if not match:
        match = re.search(r"loadNext\(\"https://www\.superookie\.com/api/jobs/search\",\s*\"([^\"]+)\"", html)
    if not match:
        raise RuntimeError("슈퍼루키 공개 검색 토큰을 찾지 못했습니다.")
    return match.group(1)


def _iso_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace(" ", "T")).date().isoformat()
    except ValueError:
        return value[:10]


def _plain(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"&nbsp;|&amp;", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _first_bullets(value: str | None, limit: int = 4) -> str:
    text = _plain(value)
    if not text:
        return ""
    parts = re.split(r"(?:\n|•|- |\* )", text)
    cleaned = [part.strip(" -•") for part in parts if len(part.strip(" -•")) > 8]
    if not cleaned:
        return text[:180]
    return ", ".join(cleaned[:limit])


def _is_finance_relevant(*parts: str) -> bool:
    text = " ".join(part for part in parts if part).lower()
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in FINANCE_PATTERNS)


def _to_job(item: dict) -> dict | None:
    job_id = str(item.get("_id") or "").strip()
    title = str(item.get("job_title_decoded") or item.get("job_title") or "").strip()
    company = str(item.get("company_name_decoded") or item.get("company_name") or "").strip()
    level = str(item.get("job_level") or "").strip()
    city = str(item.get("city") or "").strip()
    company_data = item.get("company") or {}
    work = _first_bullets(item.get("about_job"))
    requirements = _first_bullets(item.get("job_requirement"))
    advantages = _first_bullets(item.get("preference"))
    extra = _plain(item.get("additional_info"))
    search_text = " ".join([title, company, level, work, requirements, advantages, extra])

    if not job_id or not title or not company:
        return None
    if looks_senior(title, level, requirements) and not is_entry_or_intern(title, level):
        return None
    if not is_entry_or_intern(title, level):
        return None
    if not _is_finance_relevant(title, company, work, requirements, advantages, extra):
        return None

    source_url = f"{SUPEROOKIE_HOME}/jobs/{job_id}"
    apply_url = str(item.get("apply_link") or "").strip() or source_url
    deadline = _iso_date(item.get("end_at") or item.get("end_at_utc"))

    job = {
        "id": f"superookie-{job_id}",
        "title": title,
        "company": company,
        "source": "Superookie",
        "source_url": source_url,
        "apply_url": apply_url,
        "level": "intern" if "인턴" in level or "인턴" in title else "entry" if "신입" in level or "신입" in title else "",
        "employment_type": level or "확인 필요",
        "location": city or "확인 필요",
        "deadline": deadline,
        "published_at": _iso_date(item.get("published_at") or item.get("published_at_utc")),
        "description": search_text,
        "summary": {
            "work": work or "슈퍼루키 원문에서 주요업무를 확인하세요.",
            "requirements": requirements or "슈퍼루키 원문에서 지원자격을 확인하세요.",
            "advantages": advantages or "슈퍼루키 원문에서 우대사항을 확인하세요.",
            "notice": "슈퍼루키 공개 공고에서 자동 수집했습니다. 지원 전 원문 공고와 외부 지원 링크를 확인하세요.",
        },
        "status": "new",
        "featured": False,
        "hidden": False,
        "note": "",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return curate_job(job)


def collect_superookie_jobs(keywords: tuple[str, ...] = DEFAULT_KEYWORDS, pages_per_keyword: int = 2) -> list[dict]:
    token = _access_token()
    jobs: list[dict] = []
    seen: set[str] = set()

    for keyword in keywords:
        for page in range(1, max(1, pages_per_keyword) + 1):
            params = {
                "q": keyword,
                "access_token": token,
                "job_type": "job",
                "page": page,
                "short": 1,
                "page_length": 20,
            }
            payload = _fetch_json(f"{SUPEROOKIE_API_URL}?{urlencode(params)}")
            for item in payload.get("data", []) or []:
                job = _to_job(item)
                if not job or job["id"] in seen:
                    continue
                seen.add(job["id"])
                jobs.append(job)
    return jobs
