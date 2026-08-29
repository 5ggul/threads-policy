import re
import build

build.SEARCHES.extend([
 ('creator','유튜브 수익화 조건 OR 쇼츠 수익 조건 OR 유튜브 파트너 프로그램 when:60d'),
 ('creator','네이버 애드포스트 수익 OR 블로그 애드센스 수익 OR 블로그 수익화 방법 when:60d'),
 ('affiliate','쿠팡파트너스 수익 OR 제휴마케팅 수익 OR 어필리에이트 수익 when:60d'),
 ('commerce','전자책 판매 수익 OR 템플릿 판매 수익 OR 디지털 상품 판매 when:60d'),
 ('commerce','스마트스토어 부업 OR 온라인 판매 부업 OR 위탁판매 부업 when:60d'),
 ('side','크몽 부업 OR 재능판매 수익 OR 프리랜서 부업 when:60d'),
 ('creator','인스타 수익화 조건 OR Threads 수익화 OR X 수익화 조건 when:60d'),
 ('ai','AI 자동화 부업 OR ChatGPT 부업 방법 OR AI 부업 수익 when:60d'),
 ('side','재택 부업 방법 OR N잡 수익 방법 OR 투잡 수익 방법 when:60d'),
 ('apptech','앱테크 수익 OR 리워드 앱 수익 OR 포인트 앱테크 when:60d'),
])

# Duplicate clustering must not merge unrelated stories merely because both say
# "AI" or "monetization". These are discovery words, not event identifiers.
build.STOP.update({'수익화','ai','영상','기사','뉴스','플랫폼','콘텐츠','온라인','판매','조건','변경','광고'})
build.BAD = build.BAD + ('특징주','목표주가','주가','증시','ubs','sap','대기업 부업','회사 안에서 부업','일본 대기업','日대기업')

_SIDE_SCOPES={'creator','affiliate','commerce','ai','side','apptech'}
_SIDE_NOISE=('특징주','목표주가','주가','증시','실적 전망','투자의견','ubs','sap','대기업 부업','회사 안에서 부업','日대기업','일본 대기업','직원 부업 허용')
_SIDE_ACTION=('방법','하는 법','조건','요건','기준','수익화','정산','판매','가입','신청','시작','수수료','단가','정책','변경','파트너 프로그램','광고 수익','애드센스','애드포스트')

def actionable_side(text):
    t=build.clean(text).lower()
    if any(x.lower() in t for x in _SIDE_NOISE):
        return False
    pairs=(
        ('유튜브',('수익','수익화','파트너','쇼츠','광고')),
        ('블로그',('수익','수익화','애드센스','애드포스트','광고')),
        ('애드센스',('수익','광고','승인','단가','정산')),
        ('애드포스트',('수익','광고','정산','조건')),
        ('쿠팡파트너스',('수익','정산','수수료','제휴','부업')),
        ('제휴마케팅',('수익','정산','수수료','부업','방법')),
        ('어필리에이트',('수익','정산','부업','방법')),
        ('스마트스토어',('수익','매출','판매','부업','위탁')),
        ('전자책',('수익','판매','부업','정산')),
        ('템플릿',('수익','판매','부업','정산')),
        ('디지털 상품',('수익','판매','부업')),
        ('크몽',('수익','부업','재능','프리랜서','판매')),
        ('재능판매',('수익','부업','플랫폼','방법')),
        ('프리랜서',('수익','부업','플랫폼','단가')),
        ('threads',('수익','수익화','보너스','광고')),
        ('스레드',('수익','수익화','보너스','광고')),
        ('인스타',('수익','수익화','보너스','광고')),
        ('x ',('수익','수익화','광고','정산')),
        ('앱테크',('수익','리워드','포인트','정산','방법')),
        ('재택 부업',('수익','방법','플랫폼','모집','조건')),
        ('n잡',('수익','방법','플랫폼','조건')),
        ('투잡',('수익','방법','플랫폼','조건')),
    )
    mechanism=any(name in t and any(v in t for v in signals) for name,signals in pairs)
    ai_mechanism=(('ai 자동화' in t or 'chatgpt' in t or 'gpt' in t) and ('부업' in t or '수익' in t) and any(x in t for x in ('방법','자동화','판매','서비스','프리랜서','콘텐츠')))
    if not (mechanism or ai_mechanism):
        return False
    # A reusable method/policy/change is preferred over a mere "someone earned X" anecdote.
    actionable=any(x.lower() in t for x in _SIDE_ACTION)
    concrete_money=bool(re.search(r'\d[\d,]*(?:\.\d+)?\s*(?:천|만|억)?\s*원',t))
    return actionable or (concrete_money and any(x in t for x in ('방법','정산','수수료','단가','조건','판매')))

_original_items=build.items_from_xml
def strict_items(raw,source,label,scope,official=False):
    rows=_original_items(raw,source,label,scope,official)
    if scope in _SIDE_SCOPES:
        rows=[x for x in rows if actionable_side(x['title']+' '+x.get('summary',''))]
    return rows
build.items_from_xml=strict_items

build.main()
