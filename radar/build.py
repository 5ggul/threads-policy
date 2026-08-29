from __future__ import annotations

import datetime as dt
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(dt.timezone.utc)

TOPICS = [
    {
        "id": "youtube_ypp",
        "lane": "부업",
        "label": "유튜브·쇼츠",
        "query": '(유튜브 수익화 OR 쇼츠 수익화 OR YPP OR 유튜브 파트너 프로그램) when:45d',
        "must": ("유튜브", "쇼츠", "ypp"),
        "signals": ("수익", "수익화", "광고", "파트너", "조건", "정산"),
        "angle": "바뀐 수익화 조건이 기존 채널·신규 채널에 미치는 영향",
        "check": "공식 YouTube 도움말·블로그에서 적용일과 한국 적용 여부 확인",
    },
    {
        "id": "blog_ads",
        "lane": "부업",
        "label": "블로그 광고",
        "query": '(애드센스 OR 애드포스트 OR 블로그 수익화 OR 블로그 광고 수익) when:60d',
        "must": ("애드센스", "애드포스트", "블로그"),
        "signals": ("수익", "수익화", "광고", "정산", "승인", "단가", "지급"),
        "angle": "승인·정산·수익 조건 변화와 실제 운영자가 챙길 것",
        "check": "Google AdSense 또는 네이버 애드포스트 공식 공지 우선 확인",
    },
    {
        "id": "affiliate",
        "lane": "부업",
        "label": "제휴마케팅",
        "query": '(쿠팡파트너스 OR 제휴마케팅 OR 어필리에이트) (수익 OR 수수료 OR 정산 OR 정책) when:90d',
        "must": ("쿠팡파트너스", "제휴마케팅", "어필리에이트"),
        "signals": ("수익", "수수료", "정산", "정책", "링크", "광고"),
        "angle": "수수료·정산·표시의무가 바뀌면 수익 구조가 어떻게 달라지는지",
        "check": "플랫폼 약관·공정위 표시광고 기준과 실제 수수료 확인",
    },
    {
        "id": "digital_goods",
        "lane": "부업",
        "label": "디지털 판매",
        "query": '(전자책 판매 OR 템플릿 판매 OR 디지털 상품 판매 OR 노션 템플릿 판매) (수익 OR 매출 OR 부업 OR 정산) when:120d',
        "must": ("전자책", "템플릿", "디지털 상품", "노션"),
        "signals": ("판매", "수익", "매출", "부업", "정산", "수수료"),
        "angle": "재고 없이 파는 디지털 상품의 판매처·수수료·실제 진입장벽",
        "check": "판매 플랫폼 수수료와 저작권·세금 처리 확인",
    },
    {
        "id": "marketplace",
        "lane": "부업",
        "label": "온라인 판매",
        "query": '(스마트스토어 OR 온라인 판매 OR 위탁판매) (부업 OR 수익 OR 매출 OR 수수료) when:90d',
        "must": ("스마트스토어", "온라인 판매", "위탁판매"),
        "signals": ("부업", "수익", "매출", "판매", "수수료", "정산"),
        "angle": "초기비용·마진·수수료를 빼고 실제 남는 구조",
        "check": "플랫폼 판매수수료·부가세·반품비용까지 계산",
    },
    {
        "id": "freelance",
        "lane": "부업",
        "label": "프리랜서",
        "query": '(크몽 OR 재능판매 OR 프리랜서 플랫폼 OR 재택 부업) (수익 OR 단가 OR 수수료 OR 정산) when:120d',
        "must": ("크몽", "재능판매", "프리랜서", "재택"),
        "signals": ("수익", "단가", "수수료", "정산", "부업", "판매"),
        "angle": "시간당 실수익이 남는 재능판매 카테고리와 플랫폼 비용",
        "check": "플랫폼 수수료·원천징수·실제 작업시간을 함께 계산",
    },
    {
        "id": "ai_service",
        "lane": "부업",
        "label": "AI 활용",
        "query": '("AI 부업" OR "AI 자동화" OR "ChatGPT 부업" OR "AI 에이전트 수익") when:120d',
        "must": ("ai 부업", "ai 자동화", "chatgpt", "ai 에이전트"),
        "signals": ("부업", "수익", "판매", "서비스", "자동화", "프리랜서"),
        "angle": "툴 소개가 아니라 누가 무엇에 돈을 지불하는지 수익 모델로 검증",
        "check": "과장된 수익 인증 제외, 고객·가격·반복 가능성 확인",
    },
    {
        "id": "apptech",
        "lane": "부업",
        "label": "앱테크",
        "query": '(앱테크 OR 리워드 서비스 OR 포인트 적립) (출시 OR 적립 OR 혜택 OR 현금 OR 전환) when:90d',
        "must": ("앱테크", "리워드", "포인트"),
        "signals": ('현금', '출금', '적립', '포인트', '혜택', '전환', '출시', '오픈', '미션', '만보기'),
        "angle": "클릭 몇 번으로 받는 포인트가 실제 어디에 쓰이고 얼마 가치인지",
        "check": "참여 대상·포인트 전환처·이벤트 종료일·개인정보 제공 범위 확인",
    },
    {
        "id": "deposit_rates",
        "lane": "재테크",
        "label": "예적금",
        "query": '(예금금리 OR 적금금리 OR 특판예금 OR 특판적금 OR 저축은행 금리) when:14d',
        "must": ("예금", "적금", "금리"),
        "signals": ("금리", "우대", "특판", "한도", "가입", "%"),
        "angle": "광고금리 말고 우대조건을 충족했을 때 실제 세후 이자",
        "check": "금융회사 공식 상품설명서·금융상품한눈에에서 금리와 한도 확인",
    },
    {
        "id": "tax_accounts",
        "lane": "재테크",
        "label": "절세계좌",
        "query": '(ISA OR IRP OR 연금저축 OR 개인종합자산관리계좌) (세액공제 OR 비과세 OR 한도 OR 개편) when:45d',
        "must": ("isa", "irp", "연금저축", "개인종합자산관리"),
        "signals": ("세액공제", "비과세", "한도", "개편", "공제", "납입"),
        "angle": "바뀐 한도·공제율을 실제 절세액으로 환산",
        "check": "기획재정부·국세청·금융사 공식 안내에서 적용연도 확인",
    },
    {
        "id": "loan_refi",
        "lane": "재테크",
        "label": "대출·금리",
        "query": '(대환대출 OR 대출 갈아타기 OR 주담대 금리 OR 신용대출 금리) when:14d',
        "must": ("대환", "갈아타기", "대출", "주담대"),
        "signals": ("금리", "이자", "한도", "대환", "갈아타기", "%"),
        "angle": "금리 차이가 월 이자와 총이자에 얼마 차이 나는지",
        "check": "중도상환수수료·우대조건·실제 적용금리를 함께 확인",
    },
    {
        "id": "cashback",
        "lane": "혜택",
        "label": "환급·캐시백",
        "query": '(환급 OR 캐시백 OR 에너지캐시백 OR 지역화폐 캐시백) (신청 OR 지급 OR 대상 OR 조건) when:14d',
        "must": ("환급", "캐시백"),
        "signals": ("신청", "지급", "대상", "조건", "한도", "원"),
        "angle": "누가 얼마를 언제까지 신청하면 받는지 한 번에 정리",
        "check": "운영기관 공식 공고에서 대상·기간·예산소진 여부 확인",
    },
    {
        "id": "youth_support",
        "lane": "혜택",
        "label": "청년·취업",
        "query": '(청년 지원금 OR 청년수당 OR 취업지원금 OR 국민취업지원제도) (신청 OR 모집 OR 지급 OR 대상) when:21d',
        "must": ("청년", "취업지원", "지원금", "지원제도"),
        "signals": ("신청", "모집", "지급", "대상", "소득", "마감"),
        "angle": "나이·소득·지역 때문에 갈리는 실제 대상자 조건",
        "check": "고용24·지자체·사업 공식 공고에서 신청기간 확인",
    },
    {
        "id": "smallbiz_support",
        "lane": "혜택",
        "label": "소상공인",
        "query": '(소상공인 지원금 OR 소상공인 정책자금 OR 자영업자 지원) (신청 OR 접수 OR 금리 OR 지급) when:21d',
        "must": ("소상공인", "자영업자", "정책자금"),
        "signals": ("신청", "접수", "금리", "지급", "한도", "지원"),
        "angle": "현금성 지원과 대출성 정책자금을 구분해서 실제 혜택만 정리",
        "check": "소상공인시장진흥공단·중기부 공고에서 예산과 접수상태 확인",
    },
    {
        "id": "family_support",
        "lane": "혜택",
        "label": "출산·육아",
        "query": '(출산지원금 OR 육아지원금 OR 부모급여 OR 아동수당) (지급 OR 인상 OR 신청 OR 대상) when:21d',
        "must": ("출산", "육아", "부모급여", "아동수당"),
        "signals": ("지급", "인상", "신청", "대상", "월", "원"),
        "angle": "전국 공통과 지자체 추가지원금을 분리해 실제 수령액 계산",
        "check": "복지로·정부24·지자체 공고로 지역과 시행일 확인",
    },
    {
        "id": "platform_creator",
        "lane": "플랫폼",
        "label": "SNS 수익화",
        "query": '(Threads 수익화 OR 스레드 수익화 OR 인스타 수익화 OR X 수익화 OR 크리에이터 보너스) when:45d',
        "must": ("threads", "스레드", "인스타", "x 수익", "크리에이터"),
        "signals": ("수익", "수익화", "광고", "보너스", "정산", "조건"),
        "angle": "한국 계정에 실제 적용되는 수익화 기능인지 먼저 검증",
        "check": "플랫폼 공식 크리에이터 문서에서 국가·초대조건·지급조건 확인",
    },
    {
        "id": "platform_seller",
        "lane": "플랫폼",
        "label": "판매자 정책",
        "query": '(네이버 스마트스토어 정책 OR 쿠팡 판매자 정책 OR 플랫폼 수수료 인상 OR 판매자 수수료 변경) when:30d',
        "must": ("스마트스토어", "쿠팡", "판매자", "수수료"),
        "signals": ("정책", "수수료", "변경", "인상", "정산", "판매자"),
        "angle": "수수료·정산주기 변경이 실제 마진에 주는 영향",
        "check": "판매자센터 공식 공지와 적용일 확인",
    },
]

LANE_ORDER = ("부업", "재테크", "혜택", "플랫폼")
LANE_LIMITS = {"부업": 8, "재테크": 7, "혜택": 7, "플랫폼": 5}
MIN_SCORE = 69

SOURCE_SCORES = {
    "연합뉴스": 20, "뉴스1": 18, "뉴시스": 18, "한국경제": 17, "매일경제": 17,
    "서울경제": 17, "머니투데이": 17, "이데일리": 17, "아시아경제": 16,
    "파이낸셜뉴스": 15, "헤럴드경제": 15, "조선비즈": 16, "전자신문": 16,
    "zdnet": 16, "블로터": 15, "비즈워치": 15, "데일리안": 12,
    "국제뉴스": 10, "kbs": 17, "mbc": 16, "sbs": 16, "jtbc": 15,
    "금융위원회": 24, "금융감독원": 24, "한국은행": 24, "국세청": 24,
    "기획재정부": 24, "고용노동부": 24, "중소벤처기업부": 24,
    "소상공인시장진흥공단": 24, "정부24": 24, "복지로": 24,
    "youtube": 24, "google": 24, "네이버": 22, "meta": 22, "메타": 22,
    "쿠팡": 20,
}

BLOCK_GLOBAL = (
    "싱글벙글", "ㅋㅋ", "남친", "여친", "연애", "번호따", "퇴사썰", "알바썰",
    "특징주", "목표주가", "투자의견", "상한가", "급등주", "주식 추천",
    "로또", "코인 추천", "리딩방", "수익 보장", "원금 보장", "무료 강의",
    "사주", "운세", "대기업 직원 부업", "일본 대기업", "日대기업",
)
SIDE_BLOCK = ("기업 실적", "매출 전망", "주가", "증시", "투자자", "증권가", "직원 부업 허용")
FINANCE_BLOCK = ("종목", "목표가", "상장주", "코스피", "코스닥", "테마주", "주가")
BENEFIT_BLOCK = ("무산", "검토 중", "논의 중", "가능성", "공약")
GENERIC_TOKENS = {
    "수익", "수익화", "지원", "지원금", "신청", "지급", "조건", "방법", "관련",
    "이번", "오늘", "올해", "내년", "최대", "최고", "뉴스", "기자", "영상",
    "정책", "변경", "공개", "플랫폼", "부업", "재테크", "혜택", "광고",
}
ACTION_TERMS = ('신청', '접수', '마감', '대상', '자격', '조건', '정산', '수수료', '한도', '적용', '변경', '가입', '판매', '지급', '출시', '오픈', '적립', '전환')
MONEY_RE = re.compile(r'(?<!\d)(?:\d[\d,]*(?:\.\d+)?)\s*(?:천|만|억)?\s*원|(?:\d+(?:\.\d+)?)\s*[%％]')
DATE_RE = re.compile(r'(?:(?:\d{1,2})월\s*\d{1,2}일|(?:\d{4})[.\-/]\d{1,2}[.\-/]\d{1,2})')


def fetch(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MoneyHunt/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def text_of(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        el = node.find(name)
        if el is None:
            el = node.find("{*}" + name)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def source_of(node: ET.Element) -> str:
    el = node.find("source")
    if el is None:
        el = node.find("{*}source")
    return clean(el.text if el is not None else "")


def source_score(source: str) -> int:
    s = source.lower()
    return max((points for key, points in SOURCE_SCORES.items() if key.lower() in s), default=0)


def strip_source_suffix(title: str, source: str) -> str:
    title = clean(title)
    if source:
        for sep in (" - ", " | "):
            suffix = sep + source
            if title.lower().endswith(suffix.lower()):
                title = title[: -len(suffix)].strip()
    title = re.sub(r"\s+-\s+([^-]{2,30})\s+-\s+\1$", r" - \1", title)
    return title


def normalize_tokens(text: str) -> set[str]:
    words = re.findall(r"[0-9a-zA-Z가-힣]{2,}", clean(text).lower())
    return {w for w in words if w not in GENERIC_TOKENS and not w.isdigit()}


def matches_topic(topic: dict, title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    if any(b.lower() in text for b in BLOCK_GLOBAL):
        return False
    if not any(term.lower() in text for term in topic["must"]):
        return False
    if not any(term.lower() in text for term in topic["signals"]):
        return False

    lane = topic["lane"]
    if lane == "부업" and any(b.lower() in text for b in SIDE_BLOCK):
        return False
    if lane == "재테크" and any(b.lower() in text for b in FINANCE_BLOCK):
        return False
    if lane == "혜택" and any(b.lower() in text for b in BENEFIT_BLOCK):
        return False

    if lane == "혜택" and not any(x in text for x in ("신청", "접수", "지급", "대상", "마감", "기간", "한도", "캐시백")):
        return False

    if lane == '부업':
        if topic["id"] == "apptech":
            mechanism = (
                any(x in text for x in ('앱테크', '리워드', '포인트'))
                and any(x in text for x in ('적립', '전환', '출시', '오픈', '혜택', '현금', '출금', '미션', '만보기'))
            )
        elif topic["id"] == "ai_service":
            mechanism = (
                ("ai" in text or "chatgpt" in text)
                and any(x in text for x in ('부업', '수익', '판매', '프리랜서', '대행', '고객'))
            )
        else:
            mechanism = (
                any(x in text for x in ('애드센스', '애드포스트', '쿠팡파트너스', '제휴마케팅', '스마트스토어', '전자책', '템플릿', '크몽'))
                or ('유튜브' in text and any(x in text for x in ('수익', '수익화', '광고', '파트너')))
            )
        if not mechanism:
            return False
    return True


def freshness_points(published: dt.datetime | None) -> int:
    if not published:
        return 3
    hours = max(0.0, (NOW - published).total_seconds() / 3600)
    if hours <= 24:
        return 24
    if hours <= 72:
        return 20
    if hours <= 168:
        return 16
    if hours <= 24 * 30:
        return 11
    if hours <= 24 * 90:
        return 6
    return 2


def article_score(topic: dict, title: str, summary: str, source: str, published: dt.datetime | None) -> int:
    text = f"{title} {summary}".lower()
    score = 27 + freshness_points(published) + source_score(source)
    score += min(12, 3 * sum(1 for x in ACTION_TERMS if x in text))
    if MONEY_RE.search(text):
        score += 8
    if DATE_RE.search(text):
        score += 4
    if topic["id"] == "apptech" and any(x in text for x in ('출시', '오픈', '적립', '전환', '미션', '만보기')):
        score += 14
    score += min(8, 3 * sum(1 for x in topic["must"] if x.lower() in text))
    return min(99, score)


def collect_topic(topic: dict) -> tuple[list[dict], str | None]:
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(topic["query"]) + "&hl=ko&gl=KR&ceid=KR:ko"
    try:
        root = ET.fromstring(fetch(url))
    except Exception as exc:
        return [], f'{topic["id"]}: {type(exc).__name__}: {str(exc)[:90]}'

    out = []
    for node in root.findall(".//item"):
        raw_title = clean(text_of(node, ("title",)))
        summary = clean(text_of(node, ("description", "summary")))
        link = text_of(node, ("link",))
        source = source_of(node) or "출처 미상"
        published = parse_date(text_of(node, ("pubDate", "published", "updated")))
        title = strip_source_suffix(raw_title, source)
        if not title or not link or source_score(source) < 10:
            continue
        if not matches_topic(topic, title, summary):
            continue
        score = article_score(topic, title, summary, source, published)
        if score < 62:
            continue
        out.append({
            "topic_id": topic["id"],
            "lane": topic["lane"],
            "label": topic["label"],
            "title": title,
            "summary": summary,
            "url": link,
            "source": source,
            "published_at": published.isoformat() if published else None,
            "score": score,
            "tokens": sorted(normalize_tokens(title)),
            "money": MONEY_RE.findall(f"{title} {summary}")[:3],
        })
    return out, None


def same_event(a: dict, b: dict) -> bool:
    if a["topic_id"] != b["topic_id"]:
        return False
    A, B = set(a["tokens"]), set(b["tokens"])
    if not A or not B:
        return False
    hit = len(A & B)
    jaccard = hit / max(1, len(A | B))
    nums_a = set(re.findall(r"\d+(?:\.\d+)?", a["title"]))
    nums_b = set(re.findall(r"\d+(?:\.\d+)?", b["title"]))
    return jaccard >= 0.43 or hit >= 3 or (hit >= 2 and bool(nums_a & nums_b))


def cluster_articles(articles: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for article in sorted(articles, key=lambda x: x["score"], reverse=True):
        for cluster in clusters:
            if same_event(article, cluster[0]):
                cluster.append(article)
                break
        else:
            clusters.append([article])
    return clusters


def find_topic(topic_id: str) -> dict:
    return next(x for x in TOPICS if x["id"] == topic_id)


def opportunity_from_cluster(cluster: list[dict]) -> dict:
    cluster = sorted(cluster, key=lambda x: (x["score"], x["published_at"] or ""), reverse=True)
    lead = cluster[0]
    topic = find_topic(lead["topic_id"])

    by_source = {}
    for item in cluster:
        by_source.setdefault(item["source"], item)
    sources = list(by_source.values())
    source_boost = min(12, max(0, len(sources) - 1) * 5)
    official_like = any(source_score(x["source"]) >= 22 for x in sources)
    final_score = min(99, lead["score"] + source_boost + (5 if official_like else 0))

    money = []
    for item in cluster:
        for value in item.get("money", []):
            if value and value not in money:
                money.append(value)
    published_values = [x["published_at"] for x in cluster if x["published_at"]]
    published_at = max(published_values) if published_values else None

    status = "NOW" if final_score >= 88 else "PICK" if final_score >= 78 else "WATCH"
    why = {
        "부업": "수익 조건·정산·수수료처럼 실제 벌이에 연결되는 변화라서 확인 가치가 큼.",
        "재테크": "금리·세제·상품 조건이 실제 이자·세금 차이로 바로 이어지는 소재.",
        "혜택": "대상·금액·기한을 놓치면 못 받는 정보라서 선점 가치가 큼.",
        "플랫폼": "수익화·판매 정책 변화가 기존 운영 방식과 수익에 직접 영향을 줄 수 있음.",
    }[lead["lane"]]

    stable = re.sub(r"[^0-9a-z가-힣]", "", lead["title"].lower())[:40]
    return {
        "id": f'{lead["topic_id"]}-{stable}',
        "topic_id": lead["topic_id"],
        "lane": lead["lane"],
        "label": lead["label"],
        "status": status,
        "score": final_score,
        "headline": lead["title"],
        "why_now": why,
        "angle": topic["angle"],
        "check_first": topic["check"],
        "money_signal": money[:3],
        "published_at": published_at,
        "source_count": len(sources),
        "sources": [
            {"name": x["source"], "title": x["title"], "url": x["url"], "published_at": x["published_at"]}
            for x in sources[:4]
        ],
    }


def curate(opportunities: list[dict]) -> list[dict]:
    per_topic = Counter()
    lane_buckets = defaultdict(list)
    for item in sorted(opportunities, key=lambda x: (x["score"], x["source_count"]), reverse=True):
        if per_topic[item["topic_id"]] >= 1:
            continue
        per_topic[item["topic_id"]] += 1
        lane_buckets[item["lane"]].append(item)

    selected = []
    for lane in LANE_ORDER:
        selected.extend(lane_buckets[lane][: LANE_LIMITS[lane]])
    selected.sort(key=lambda x: (x["status"] == "NOW", x["score"], x["source_count"]), reverse=True)
    return selected[:27]


def render(data: dict) -> str:
    items = data["items"]
    counts = data["counts"]
    now_count = sum(1 for x in items if x["status"] == "NOW")

    cards = []
    for item in items:
        money = " · ".join(item["money_signal"]) if item["money_signal"] else "금액은 원문 확인"
        source_links = "".join(
            f'<a href="{html.escape(src["url"])}" target="_blank" rel="noopener">{html.escape(src["name"])}</a>'
            for src in item["sources"]
        )
        search_text = " ".join([
            item["headline"], item["lane"], item["label"], item["why_now"],
            item["angle"], item["check_first"], money,
        ]).lower()
        cards.append(f'''
        <article class="card" data-lane="{html.escape(item["lane"])}" data-status="{item["status"]}" data-q="{html.escape(search_text)}">
          <div class="card-top">
            <div class="chips"><span class="status {item["status"].lower()}">{item["status"]}</span><span class="lane">{html.escape(item["lane"])}</span><span class="label">{html.escape(item["label"])}</span></div>
            <div class="score">{item["score"]}</div>
          </div>
          <h2>{html.escape(item["headline"])}</h2>
          <div class="money">{html.escape(money)}</div>
          <div class="detail"><span>왜 지금</span><p>{html.escape(item["why_now"])}</p></div>
          <div class="detail"><span>콘텐츠 각도</span><p>{html.escape(item["angle"])}</p></div>
          <div class="detail check"><span>먼저 확인</span><p>{html.escape(item["check_first"])}</p></div>
          <div class="foot"><div class="source-meta">근거 {item["source_count"]}개</div><div class="links">{source_links}</div></div>
        </article>''')

    lane_buttons = "".join(
        f'<button class="filter" data-lane="{lane}">{lane}<b>{counts.get(lane, 0)}</b></button>'
        for lane in LANE_ORDER
    )

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>MONEY HUNT</title>
<style>
:root{{--bg:#07090d;--panel:#0e1219;--line:#222b3a;--text:#f3f6fa;--muted:#8894a6}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 20% -10%,#182234 0,transparent 34%),var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,"Pretendard","Malgun Gothic",sans-serif}}
.wrap{{max-width:1480px;margin:auto;padding:34px 22px 80px}} .eyebrow{{font-size:12px;letter-spacing:.18em;color:#77869a;font-weight:800}}
h1{{font-size:42px;line-height:1;margin:9px 0 10px;letter-spacing:-.04em}} .hero p{{margin:0;color:#9ba7b8;font-size:14px}}
.hero{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:24px}} .updated{{color:#687589;font-size:12px;white-space:nowrap}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}} .kpi{{background:rgba(14,18,25,.88);border:1px solid var(--line);border-radius:14px;padding:14px 16px}}
.kpi span{{display:block;color:#7f8da0;font-size:11px;margin-bottom:5px}} .kpi b{{font-size:24px}}
.toolbar{{display:flex;gap:8px;align-items:center;margin:16px 0 18px;flex-wrap:wrap}} .filter{{border:1px solid var(--line);background:#0c1118;color:#aeb8c7;border-radius:11px;padding:9px 11px;cursor:pointer}}
.filter b{{margin-left:7px;color:#617086}} .filter.on{{color:white;background:#1b2636;border-color:#3c506a}} #search{{margin-left:auto;min-width:260px;background:#0b1017;border:1px solid var(--line);color:white;border-radius:11px;padding:10px 12px;outline:none}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}} .card{{background:linear-gradient(180deg,rgba(17,23,33,.97),rgba(12,16,23,.97));border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 14px 38px rgba(0,0,0,.13)}}
.card-top{{display:flex;justify-content:space-between;gap:10px;align-items:center}} .chips{{display:flex;gap:5px;flex-wrap:wrap}} .chips span{{font-size:10px;padding:4px 7px;border-radius:999px;border:1px solid #2a3444;color:#9ca9bb}}
.status.now{{border-color:#6c4b25;color:#ffc477;background:#241b11}} .status.pick{{color:#a9caff;border-color:#344d70}} .score{{font-weight:800;font-size:18px;color:#6e7e92}}
.card h2{{font-size:17px;line-height:1.48;letter-spacing:-.02em;margin:13px 0 9px}} .money{{font-size:12px;color:#94dcb7;background:#0d1c18;border:1px solid #19372e;display:inline-block;border-radius:8px;padding:6px 8px;margin-bottom:12px}}
.detail{{border-top:1px solid #1c2430;padding-top:10px;margin-top:9px}} .detail span{{display:block;color:#67768a;font-size:10px;font-weight:800;letter-spacing:.05em;margin-bottom:4px}} .detail p{{margin:0;color:#b5bfcc;font-size:12.5px;line-height:1.55}}
.detail.check p{{color:#d6dde7}} .foot{{border-top:1px solid #1c2430;margin-top:12px;padding-top:11px;display:flex;justify-content:space-between;gap:9px;align-items:flex-start}} .source-meta{{font-size:10px;color:#647286;white-space:nowrap}}
.links{{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}} .links a{{font-size:10px;text-decoration:none;color:#8fb8ef;border:1px solid #263b55;border-radius:7px;padding:4px 6px}}
.empty{{display:none;text-align:center;color:#6c7889;padding:70px 10px}} .rules{{margin-top:22px;color:#596677;font-size:11px;line-height:1.6}}
@media(max-width:1100px){{.grid{{grid-template-columns:repeat(2,1fr)}}.kpis{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:720px){{.wrap{{padding:24px 12px 55px}}h1{{font-size:34px}}.hero{{display:block}}.updated{{margin-top:10px}}.kpis{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}#search{{order:2;width:100%;margin-left:0}}}}
</style>
</head>
<body>
<main class="wrap">
  <section class="hero">
    <div><div class="eyebrow">EDITORIAL OPPORTUNITY RADAR</div><h1>MONEY HUNT</h1><p>기사 개수는 버린다. 실제로 돈·콘텐츠로 연결할 수 있는 기회만 남긴다.</p></div>
    <div class="updated">UPDATED {html.escape(data["generated_at"])}</div>
  </section>
  <section class="kpis">
    <div class="kpi"><span>오늘 바로 볼 것</span><b>{now_count}</b></div>
    <div class="kpi"><span>부업</span><b>{counts.get("부업",0)}</b></div>
    <div class="kpi"><span>재테크</span><b>{counts.get("재테크",0)}</b></div>
    <div class="kpi"><span>혜택</span><b>{counts.get("혜택",0)}</b></div>
    <div class="kpi"><span>플랫폼 변화</span><b>{counts.get("플랫폼",0)}</b></div>
  </section>
  <div class="toolbar">
    <button class="filter on" data-lane="all">전체<b>{len(items)}</b></button>
    <button class="filter" data-lane="NOW">NOW<b>{now_count}</b></button>
    {lane_buttons}
    <input id="search" placeholder="소재·플랫폼·지원금 검색">
  </div>
  <section class="grid" id="grid">{''.join(cards)}</section>
  <div class="empty" id="empty">조건을 통과한 소재가 없다.</div>
  <div class="rules">차단: 커뮤니티 잡담 · 종목추천/목표주가 · 기업 실적을 부업으로 오분류 · 해외 직장문화 사례 · 수익보장/리딩방 · 검토중인 지원금 · 한 사건의 기사 중복. 품질 기준 미달이면 숫자를 채우지 않음.</div>
</main>
<script>
let lane='all'; const search=document.getElementById('search');
function apply(){{
  const q=search.value.trim().toLowerCase(); let shown=0;
  document.querySelectorAll('.card').forEach(card=>{{
    const laneOk=lane==='all'||card.dataset.lane===lane||(lane==='NOW'&&card.dataset.status==='NOW');
    const qOk=!q||card.dataset.q.includes(q); const visible=laneOk&&qOk;
    card.style.display=visible?'':'none'; if(visible) shown++;
  }});
  document.getElementById('empty').style.display=shown?'none':'block';
}}
document.querySelectorAll('.filter').forEach(btn=>btn.onclick=()=>{{
 document.querySelectorAll('.filter').forEach(x=>x.classList.remove('on')); btn.classList.add('on'); lane=btn.dataset.lane; apply();
}});
search.oninput=apply;
</script>
</body></html>'''


def main() -> None:
    all_articles = []
    errors = []
    topic_raw_counts = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(collect_topic, topic): topic for topic in TOPICS}
        for future in as_completed(future_map):
            topic = future_map[future]
            try:
                rows, error = future.result()
            except Exception as exc:
                rows, error = [], f'{topic["id"]}: {type(exc).__name__}: {str(exc)[:90]}'
            topic_raw_counts[topic["id"]] = len(rows)
            all_articles.extend(rows)
            if error:
                errors.append(error)

    clusters = cluster_articles(all_articles)
    opportunities = [opportunity_from_cluster(c) for c in clusters]
    opportunities = [x for x in opportunities if x["score"] >= MIN_SCORE]
    curated = curate(opportunities)

    counts = {lane: sum(1 for x in curated if x["lane"] == lane) for lane in LANE_ORDER}
    data = {
        "generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "counts": counts,
        "items": curated,
        "meta": {
            "raw_articles": len(all_articles),
            "event_clusters": len(clusters),
            "shown": len(curated),
            "topic_raw_counts": topic_raw_counts,
            "errors": errors,
        },
    }
    (ROOT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "index.html").write_text(render(data), encoding="utf-8")
    print("MONEY_HUNT_OK", data["counts"], data["meta"])
    for item in curated:
        print(f'[{item["lane"]}] {item["score"]} {item["headline"]} / sources={item["source_count"]}')


if __name__ == "__main__":
    main()
