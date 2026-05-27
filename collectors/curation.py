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
NON_TARGET_LEVEL_KEYWORDS = ("주니어경력", "junior career")
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

TAG_PATTERNS = {
    "IB": (
        r"\binvestment banking\b",
        r"\bIB\b",
        r"\bM&A\b",
        r"\bECM\b",
        r"\bDCM\b",
        r"\bIPO\b",
        r"기업금융",
        r"인수금융",
        r"deal execution",
        r"pitchbook",
    ),
    "자산운용": (r"자산운용", r"운용역", r"펀드", r"\bportfolio management\b", r"\basset management\b"),
    "리서치": (r"리서치", r"\bresearch\b", r"\bRA\b", r"애널리스트", r"산업\s*분석", r"기업\s*분석"),
    "증권": (r"증권", r"\bsecurities\b", r"\bsecurities research\b", r"\bbrokerage\b"),
    "퀀트": (r"퀀트", r"\bquant\b", r"파생", r"\bderivative", r"알고리즘"),
    "리스크": (r"리스크", r"\brisk\b", r"심사", r"\bcredit\b", r"신용"),
    "WM": (
        r"\bwealth management\b",
        r"\bprivate banking\b",
        r"\bPB\b",
        r"프라이빗뱅커",
        r"고객자산",
        r"자산관리\s*(?:영업|컨설팅|PB|WM)?",
    ),
    "핀테크": (r"핀테크", r"\bfintech\b", r"\bpayment", r"페이먼트"),
    "외국계": (r"외국계", r"\bforeign[-\s]?owned\b", r"\bmultinational\b", r"\bkorea branch\b", r"한국\s*지사"),
    "백오피스": (r"결제", r"\bsettlement\b", r"운용지원", r"컴플라이언스", r"준법", r"오퍼레이션"),
}

ROLE_FINANCE_PATTERNS = (
    r"금융",
    r"증권",
    r"은행",
    r"보험\s*(?:리스크|계리|IFRS|K-ICS|금융|상품|부채|자본)",
    r"자산운용",
    r"운용역",
    r"펀드",
    r"채권",
    r"주식",
    r"파생",
    r"리스크",
    r"신용",
    r"여신",
    r"기업\s*심사",
    r"기업금융",
    r"전략금융",
    r"인수금융",
    r"투자은행",
    r"투자자",
    r"재무모델",
    r"재무\s*실사",
    r"가치평가",
    r"밸류에이션",
    r"회계감사",
    r"결산",
    r"\bIB\b",
    r"\bM&A\b",
    r"\bECM\b",
    r"\bDCM\b",
    r"\bPE\b",
    r"\bVC\b",
    r"\bIPO\b",
    r"\bfintech\b",
    r"\bfinance\b",
    r"\bfinancial institutions?\b",
    r"\bfinancial markets?\b",
    r"\bwholesale banking\b",
    r"\bstructured finance\b",
    r"\btransaction services?\b",
    r"\blending\b",
    r"\bsecurities\b",
    r"\basset management\b",
    r"\binvestment banking\b",
    r"\bcapital markets?\b",
    r"\bvaluation\b",
    r"\brisk management\b",
    r"\bportfolio\b",
    r"\bcredit\b",
)

NON_FINANCE_ROLE_PATTERNS = (
    r"\bexecutive assistant\b",
    r"CEO\)?\s*의\s*시간",
    r"비서",
    r"경영지원",
    r"총무",
    r"상품권",
    r"사택",
    r"시설\s*관리",
    r"IT\s*운영",
    r"IT\s*개발",
    r"정보보안",
    r"모의해킹",
    r"인사",
    r"채용\s*(?:담당|운영|매니저)",
    r"관세",
    r"FTA\s*원산지",
    r"해외시장조사",
    r"이사회",
    r"주주총회",
    r"법인\s*관련\s*문서",
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", value).strip()


def has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def slugify(value: str) -> str:
    value = normalize_text(value).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "job"


def is_finance_relevant(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    return any(keyword in text for keyword in FINANCE_KEYWORDS)


def is_finance_role_relevant(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part) for part in parts if part)
    return has_any_pattern(text, ROLE_FINANCE_PATTERNS)


def is_non_finance_role(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part) for part in parts if part)
    return has_any_pattern(text, NON_FINANCE_ROLE_PATTERNS)


def is_entry_or_intern(*parts: str | None) -> bool:
    return detect_level(*parts) in {"intern", "entry"}


def has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def detect_level(*parts: str | None) -> str:
    normalized_parts = [normalize_text(part).lower() for part in parts if part]
    title_text = normalized_parts[0] if normalized_parts else ""
    text = " ".join(normalized_parts)
    if has_keyword(text, NON_TARGET_LEVEL_KEYWORDS):
        return "unknown"
    if has_keyword(title_text, INTERN_KEYWORDS):
        return "intern"
    if has_keyword(title_text, ENTRY_KEYWORDS):
        return "entry"
    if "채용전환" in text and has_keyword(text, INTERN_KEYWORDS):
        return "intern"
    if has_keyword(text, ENTRY_KEYWORDS):
        return "entry"
    if has_keyword(text, INTERN_KEYWORDS) and not re.search(r"(인턴\s*등|인턴\s*경험|경험\s*\(?\s*인턴|인턴십\s*경험)", text):
        return "intern"
    return "unknown"


def looks_senior(*parts: str | None) -> bool:
    text = " ".join(normalize_text(part).lower() for part in parts if part)
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def detect_employment_type(level: str, *parts: str | None) -> str:
    text = " ".join(normalize_text(part) for part in parts if part)
    title_text = normalize_text(parts[0]).lower() if parts else ""
    if level == "intern" and "채용전환" in text:
        return "채용전환형 인턴"
    if level == "intern" or has_keyword(title_text, INTERN_KEYWORDS):
        return "인턴"
    if level == "entry":
        return "신입"
    return "확인 필요"


def detect_tags(*parts: str | None) -> list[str]:
    text = " ".join(normalize_text(part) for part in parts if part)
    title_company_text = " ".join(normalize_text(part) for part in parts[:2] if part)
    tags: list[str] = []
    for tag, patterns in TAG_PATTERNS.items():
        target_text = title_company_text if tag == "증권" else text
        if has_any_pattern(target_text, patterns):
            tags.append(tag)
    level = detect_level(*parts)
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
