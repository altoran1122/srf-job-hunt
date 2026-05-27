from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .curation import (
    curate_job,
    is_entry_or_intern,
    looks_senior,
    slugify,
)


KOFIA_LIST_URL = "https://kofia.or.kr/brd/m_96/list.do"
USER_AGENT = "SRF-Job-Hunt/0.1 (+personal curation board)"


class KofiaListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None
        self._capture_cell = False
        self._capture_link = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._capture_cell = True
            self._cell = {"text": "", "href": ""}
        elif tag == "a" and self._capture_cell and self._cell is not None:
            href = attrs_dict.get("href") or ""
            if "view.do" in href:
                self._cell["href"] = href
                self._capture_link = True

    def handle_data(self, data: str) -> None:
        if self._capture_cell and self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._capture_link = False
        elif tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._cell["text"] = " ".join(self._cell["text"].split())
            self._row.append(self._cell)
            self._cell = None
            self._capture_cell = False
        elif tag == "tr" and self._row is not None:
            if len(self._row) >= 4:
                self.rows.append(self._row)
            self._row = None
            self._cell = None
            self._capture_cell = False
            self._capture_link = False


class KofiaDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag in {"br", "p", "div", "li", "tr"} and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "li", "tr"} and not self._skip_depth:
            self.parts.append("\n")

    def text(self) -> str:
        text = " ".join(" ".join(self.parts).split())
        return re.sub(r"\s+", " ", text).strip()


def _fetch(url: str, timeout: int = 12) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _detail_text(url: str) -> str:
    parser = KofiaDetailParser()
    parser.feed(_fetch(url, timeout=6))
    text = parser.text()
    return text[:5000]


def _page_url(page: int) -> str:
    if page <= 1:
        return KOFIA_LIST_URL
    return f"{KOFIA_LIST_URL}?{urlencode({'pageIndex': page})}"


def _row_to_job(row: list[dict], fetch_detail: bool = True) -> dict | None:
    texts = [cell.get("text", "") for cell in row]
    link = next((cell.get("href", "") for cell in row if cell.get("href")), "")
    if len(texts) < 5 or not link:
        return None

    company = texts[1]
    title = texts[2]
    published_at = texts[-1]
    source_url = urljoin(KOFIA_LIST_URL, link)
    preliminary_text = " ".join(part for part in (title, company) if part)

    if not title or not company:
        return None
    if looks_senior(preliminary_text) and not is_entry_or_intern(preliminary_text):
        return None
    if not fetch_detail and not is_entry_or_intern(preliminary_text):
        return None

    detail_text = ""
    if fetch_detail:
        try:
            detail_text = _detail_text(source_url)
        except Exception:
            detail_text = ""
    check_text = " ".join(part for part in (title, company, detail_text) if part)

    if looks_senior(check_text) and not is_entry_or_intern(check_text):
        return None
    if not is_entry_or_intern(check_text):
        return None

    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)
    sequence = query.get("seq", [""])[0] or slugify(f"{company}-{title}")

    job = {
        "id": f"kofia-{sequence}",
        "title": title,
        "company": company,
        "source": "KOFIA",
        "source_url": source_url,
        "apply_url": source_url,
        "location": "확인 필요",
        "published_at": published_at,
        "description": detail_text,
        "summary": {
            "work": detail_text[:700] if detail_text else "KOFIA 원문에서 주요업무를 확인하세요.",
            "requirements": "KOFIA 상세 공고에서 지원자격과 제출서류를 확인하세요.",
            "advantages": "KOFIA 상세 공고에서 우대사항을 확인하세요.",
            "notice": "KOFIA 채용공고 상세 페이지까지 확인해 자동 수집했습니다. 지원 전 원문과 첨부파일을 확인하세요.",
        },
        "status": "new",
        "featured": False,
        "hidden": False,
        "note": "",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    return curate_job(job)


def collect_kofia_jobs(max_pages: int = 10, fetch_details: bool = True) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        parser = KofiaListParser()
        try:
            parser.feed(_fetch(_page_url(page)))
        except Exception:
            continue
        for row in parser.rows:
            job = _row_to_job(row, fetch_detail=fetch_details)
            if not job or job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)

    return jobs
