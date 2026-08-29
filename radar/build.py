from __future__ import annotations
import datetime as dt, html, json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).parent
SEARCHES=[
 ('benefit','지원금 OR 장려금 OR 환급금 OR 바우처 OR 캐시백 when:3d'),
 ('policy','청년 지원사업 OR 소상공인 지원사업 OR 창업 지원사업 when:7d'),
 ('tax','세액공제 OR 소득공제 OR 절세 OR 환급 when:5d'),
 ('investment','예금 금리 OR 적금 금리 OR ISA OR IRP OR 연금저축 when:5d'),
 ('loan','대출 갈아타기 OR 대환대출 OR 금리 우대 OR 정책대출 when:5d'),
 ('creator','애드센스 OR 블로그 수익 OR 유튜브 수익화 OR Threads 수익 OR X 수익 when:7d'),
 ('side','부업 OR N잡 OR 투잡 OR 재택 부업 OR 월급 외 수입 when:7d'),
 ('commerce','스마트스토어 OR 쿠팡파트너스 OR 제휴마케팅 OR 전자책 판매 OR 템플릿 판매 when:7d'),
 ('ai','AI 부업 OR AI 자동화 수익 OR 노코드 부업 when:7d'),
]
OFFICIAL=[
 ('policy:mss','중소벤처기업부','https://mss.go.kr/rss/smba/board/310.do'),
 ('policy:moel','고용노동부','https://www.moel.go.kr/rss/policy.do'),
]
BAD=('싱글벙글','알바 썰','알바썰','퇴사 썰','퇴사썰','직장 썰','직장썰','은퇴한 알바','번호따','번호 따','남친','여친','ㅋㅋ','리딩방','무료 강의','무료강의','수익 보장','원금 보장')
MONEY=('지원금','장려금','보조금','바우처','환급','세액공제','소득공제','절세','예금','적금','isa','irp','연금저축','대출','대환','금리','애드센스','블로그 수익','유튜브 수익','수익화','부업','n잡','투잡','재택 부업','스마트스토어','쿠팡파트너스','제휴마케팅','전자책','템플릿 판매','ai 부업','앱테크','정책자금','지원사업')
ACTION=('신청','접수','마감','대상','자격','조건','방법','모집','정산','금리','한도','지원기간','신청기간','지급','지원')
AMOUNT=re.compile(r'(?:\d[\d,]*(?:\.\d+)?\s*(?:천|만|억)?\s*원|\d+(?:\.\d+)?\s*[%％])')
STOP={'지원금','지원','혜택','신청','지급','환급','부업','수익','돈','정보','관련','오늘','이번','공개','시작','모집','방법','사업','공고','정부','정책','신규','대상'}

def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TweetRadarPages/1.0'})
 with urllib.request.urlopen(req,timeout=20) as r:return r.read()
def clean(s):return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',s or '')).strip()
def parse_date(s):
 try:
  from email.utils import parsedate_to_datetime
  d=parsedate_to_datetime(s);return d.astimezone(dt.timezone.utc).isoformat()
 except Exception:return None
def toks(s):return {x for x in re.sub(r'[^0-9a-z가-힣]+',' ',s.lower()).split() if len(x)>=2 and x not in STOP}
def sim(a,b):
 A,B=toks(a),toks(b); hit=len(A&B)
 if hit<2:return 0
 j=hit/max(1,len(A|B));return max(j,.55 if hit>=4 else .42 if hit==3 else j)
def group(scope,title):
 t=title.lower()
 if scope=='policy' or any(x in t for x in ('지원금','장려금','보조금','바우처','환급','세액공제','지원사업','정책자금')):return '혜택·정책'
 if scope in ('investment','loan','tax') or any(x in t for x in ('예금','적금','isa','irp','연금저축','대출','금리','절세')):return '재테크·절세'
 return '부업·수익'
def score(title,desc,official=False):
 text=(title+' '+desc).lower()
 if any(x in text for x in BAD):return 0
 hits=sum(1 for x in MONEY if x in text); actions=sum(1 for x in ACTION if x in text); amount=bool(AMOUNT.search(text))
 if not official and hits==0:return 0
 if not official and actions==0 and not amount and hits<2:return 0
 return min(99,45+hits*7+actions*5+(12 if amount else 0)+(18 if official else 0))
def items_from_xml(raw,source,label,scope,official=False):
 root=ET.fromstring(raw); out=[]
 for node in list(root.findall('.//item'))+list(root.findall('.//{*}entry')):
  def txt(names):
   for n in names:
    e=node.find(n) or node.find('{*}'+n)
    if e is not None and (e.text or '').strip():return e.text.strip()
   return ''
  title=clean(txt(['title'])); desc=clean(txt(['description','summary','content'])); link=txt(['link'])
  le=node.find('link') or node.find('{*}link')
  if not link and le is not None:link=le.attrib.get('href','')
  published=parse_date(txt(['pubDate','published','updated']))
  if not title or not link:continue
  sc=score(title,desc,official)
  if sc<52:continue
  out.append({'title':title,'url':link,'source':source,'source_label':label,'scope':scope,'group':group(scope,title),'score':sc,'official':official,'published_at':published,'amount':(AMOUNT.search(title+' '+desc).group(0) if AMOUNT.search(title+' '+desc) else ''),'summary':desc[:260]})
 return out
