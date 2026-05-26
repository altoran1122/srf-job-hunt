from __future__ import annotations

from datetime import date
import re
import unicodedata


FINANCE_KEYWORDS = (
    "금융",
    "증권",
    "자산운용",
    "운용",
    "투자",
    "은행",
    "캐피탈",
    "카드",
    "보험",
    "리서치",
    "애널리스트",
    "ib",
    "m&a",
    "ecm",
    "dcm",
    "pe",
    "vc",
    "퀀트",
    "리스크",
    "핀테크",
    "fund",
    "asset",
    "securities",
    "bank",
    "finance",
    "investment",
)

ENTRY_KEYWORDS = ("신입", "주니어", "채용전환", "trainee", "analyst", "entry")
INTERN_KEYWORDS = ("인턴", "intern", "internship")
EXCLUDE_KEYWORDS = (
    "경력직",
    "경력",
    "팀장",
    "본부장",
    "부문장",
    "임원",
    "시니어",
    "senior",
    "manager",
    "lead",
    "10년",
    "7년",
    "5년",
    "4년",
    "3년",
)

TAG_RULES = {
    "IB": ("ib", "investment banking", "m&a", "ecm", "dcm", "기업금융", "인수금융"),
    "자산운용": ("자산운용", "운용", "펀드", "portfolio", "asset management"),
    "리서치": ("리서치", "research", "ra", "애널리스트", "분석"),
    "퀀트": ("퀀트", "quant", "파생", "derivative", "알고리즘"),
    "리스크": ("리스크", "risk", "심사", "credit", "신용"),
    "WM": ("wm", "wealth", "pb", "프라이빗뱅커", "고객자산"),
    "핀테크": ("핀테크", "fintech", "데이터", "플랫폼", "payment", "페이먼트"),
    "외국계": ("외국계", "global", "korea branch", "english", "영문", "영어"),
    "백오피스": ("결제", "settlement", "운용지원", "컴플라이언스", "준법", "오퍼레이션"),
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = normalize_text(value).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "job"


def is_finance_relevant(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    return any(keyword in text for keyword in FINANCE_KEYWORDS)


def is_entry_or_intern(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    if any(keyword in text for keyword in INTERN_KEYWORDS):
        return True
    if any(keyword in text for keyword in ENTRY_KEYWORDS):
        return True
    return False


def looks_senior(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def detect_level(*parts: str | None) -> str:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    if any(keyword in text for keyword in INTERN_KEYWORDS):
        return "intern"
    if any(keyword in text for keyword in ENTRY_KEYWORDS):
        return "entry"
    return "unknown"


def detect_employment_type(level: str, *parts: str | None) -> str:
    text = " ".join(normalize_text(part) for part in parts if part)
    lowered = text.lower()
    if "채용전환" in text:
        return "채용전환형 인턴"
    if any(keyword in lowered for keyword in INTERN_KEYWORDS):
        return "인턴"
    if level == "entry":
        return "신입"
    return "확인 필요"


def detect_tags(*parts: str | None) -> list[str]:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    tags: list[str] = []
    for tag, keywords in TAG_RULES.items():
        if any(keyword.lower() in text for keyword in keywords):
            tags.append(tag)
    level = detect_level(text)
    if level == "intern":
        tags.append("인턴")
    elif level == "entry":
        tags.append("신입")
    return tags[:6]


def parse_deadline(*parts: str | None) -> str:
    text = " ".join(normalize_text(part) for part in parts if part)
    current_year = date.today().year
    patterns = (
        r"(?:~|마감|까지)\s*(20\d{2})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})",
        r"(?:~|마감|까지)\s*(\d{1,2})[./-]\s*(\d{1,2})",
        r"(\d{1,2})월\s*(\d{1,2})일",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if not match:
            continue
        if index == 0:
            year, month, day = match.groups()
        else:
            year = str(current_year)
            month, day = match.groups()
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return ""
    if "채용시" in text or "상시" in text:
        return "상시"
    return ""


def make_summary(job: dict) -> dict:
    title = normalize_text(job.get("title"))
    company = normalize_text(job.get("company")) or "해당 회사"
    tags = job.get("tags") or detect_tags(title, job.get("description"))
    tag_text = ", ".join(tags[:3]) if tags else "금융권"
    level = job.get("level") or detect_level(title, job.get("description"))

    level_text = "인턴" if level == "intern" else "신입" if level == "entry" else "신입/인턴"
    source = normalize_text(job.get("source")) or "원문"
    deadline = normalize_text(job.get("deadline"))
    deadline_text = f" 마감일은 {deadline}로 보입니다." if deadline else " 마감일은 원문 확인이 필요합니다."

    return {
        "work": f"{company}의 {title} 공고입니다. {tag_text} 관련 업무 가능성이 높습니다.",
        "requirements": f"{level_text}급 공고로 분류했습니다. 세부 지원자격과 제출서류는 {source} 원문에서 확인하세요.",
        "advantages": "금융시장 이해, 데이터 정리, 영어 또는 Excel 역량이 있으면 우대 포인트가 될 수 있습니다.",
        "fit": f"{tag_text} 커리어를 탐색하는 SRF 멤버에게 우선 검토할 만한 공고입니다.",
        "notice": f"자동 요약입니다.{deadline_text} 지원 전 원문 공고를 확인하세요.",
    }


def curate_job(job: dict) -> dict:
    title = normalize_text(job.get("title"))
    company = normalize_text(job.get("company"))
    description = normalize_text(job.get("description"))
    level = job.get("level") or detect_level(title, description)
    deadline = job.get("deadline") or parse_deadline(title, description)
    tags = job.get("tags") or detect_tags(title, company, description)

    curated = dict(job)
    curated["title"] = title
    curated["company"] = company
    curated["level"] = level
    curated["employment_type"] = job.get("employment_type") or detect_employment_type(level, title, description)
    curated["deadline"] = deadline
    curated["tags"] = tags
    curated["summary"] = job.get("summary") or make_summary(curated)
    return curated
