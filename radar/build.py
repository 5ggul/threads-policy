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
MONEY=('지원금','장려금','보조금','바우처','환급','세액공제','소득공제','절세','예금','적금','isa','irp','연금저축','대출','대환','금리','애드센스','블로그 수익','유튜브 수익','수익화','부업','n잡','투잡','재택 부업','스마트스토어','쿠팡파트너스','제휴마케팅','전자책','템플릿 판매','ai 부업','앱테크','정책자금','지원사업','창업지원','소상공인')
ACTION=('신청','접수','마감','대상','자격','조건','방법','모집','정산','금리','한도','지원기간','신청기간','지급','지원','공고')
AMOUNT=re.compile(r'(?:\d[\d,]*(?:\.\d+)?\s*(?:천|만|억)?\s*원|\d+(?:\.\d+)?\s*[%％])')
STOP={'지원금','지원','혜택','신청','지급','환급','부업','수익','돈','정보','관련','오늘','이번','공개','시작','모집','방법','사업','공고','정부','정책','신규','대상','대한','위한'}

def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TweetRadarPages/1.0'})
 with urllib.request.urlopen(req,timeout=20) as r:return r.read()
def clean(s):return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',s or '')).strip()
def parse_date(s):
 try:
  from email.utils import parsedate_to_datetime
  return parsedate_to_datetime(s).astimezone(dt.timezone.utc).isoformat()
 except Exception:return None
def toks(s):return {x for x in re.sub(r'[^0-9a-z가-힣]+',' ',s.lower()).split() if len(x)>=2 and x not in STOP}
def sim(a,b):
 A,B=toks(a),toks(b); hit=len(A&B)
 if hit<2:return 0
 j=hit/max(1,len(A|B));return max(j,.55 if hit>=4 else .42 if hit==3 else j)
def category(scope,title):
 t=title.lower()
 if scope=='policy' or any(x in t for x in ('지원금','장려금','보조금','바우처','환급','세액공제','지원사업','정책자금','소상공인')):return '혜택·정책'
 if scope in ('investment','loan','tax') or any(x in t for x in ('예금','적금','isa','irp','연금저축','대출','금리','절세')):return '재테크·절세'
 return '부업·수익'
def score(title,desc,official=False):
 text=(title+' '+desc).lower()
 if any(x in text for x in BAD):return 0
 hits=sum(1 for x in MONEY if x in text); actions=sum(1 for x in ACTION if x in text); amount=bool(AMOUNT.search(text))
 if not official and hits==0:return 0
 if not official and actions==0 and not amount and hits<2:return 0
 return min(99,45+hits*7+actions*5+(12 if amount else 0)+(18 if official else 0))
def find_text(node,names):
 for name in names:
  el=node.find(name)
  if el is None:el=node.find('{*}'+name)
  if el is not None and (el.text or '').strip():return el.text.strip()
 return ''
def items_from_xml(raw,source,label,scope,official=False):
 root=ET.fromstring(raw); out=[]
 nodes=list(root.findall('.//item'))+list(root.findall('.//{*}entry'))
 for node in nodes:
  title=clean(find_text(node,['title'])); desc=clean(find_text(node,['description','summary','content'])); link=find_text(node,['link'])
  le=node.find('link')
  if le is None:le=node.find('{*}link')
  if not link and le is not None:link=le.attrib.get('href','')
  published=parse_date(find_text(node,['pubDate','published','updated']))
  if not title or not link:continue
  sc=score(title,desc,official)
  if sc<52:continue
  m=AMOUNT.search(title+' '+desc)
  out.append({'title':title,'url':link,'source':source,'source_label':label,'scope':scope,'category':category(scope,title),'score':sc,'official':official,'published_at':published,'amount':m.group(0).strip() if m else '','summary':desc[:280]})
 return out

def collect():
 rows=[]; errors=[]
 for scope,q in SEARCHES:
  url='https://news.google.com/rss/search?q='+urllib.parse.quote(q)+'&hl=ko&gl=KR&ceid=KR:ko'
  try: rows+=items_from_xml(fetch(url),'news:'+scope,'Google News · '+scope,scope,False)
  except Exception as e:errors.append(scope+': '+str(e)[:100])
 for source,label,url in OFFICIAL:
  try: rows+=items_from_xml(fetch(url),source,label,'policy',True)
  except Exception as e:errors.append(source+': '+str(e)[:100])
 exact=set(); unique=[]
 for x in sorted(rows,key=lambda z:(z['official'],z['score'],z.get('published_at') or ''),reverse=True):
  key=re.sub(r'[^0-9a-z가-힣]','',x['title'].lower())
  if key in exact:continue
  exact.add(key)
  rep=next((y for y in unique if y['category']==x['category'] and sim(y['title'],x['title'])>=.42),None)
  if rep:
   rep.setdefault('related',[]).append({'title':x['title'],'url':x['url'],'source_label':x['source_label']})
   rep['score']=max(rep['score'],x['score']);continue
  x['related']=[];unique.append(x)
 # category diversity: round robin, then remainder
 groups={c:[] for c in ('혜택·정책','재테크·절세','부업·수익')}
 for x in unique:groups[x['category']].append(x)
 for a in groups.values():a.sort(key=lambda z:(z['official'],z['score'],z.get('published_at') or ''),reverse=True)
 balanced=[]
 while len(balanced)<90 and any(groups.values()):
  for c in ('혜택·정책','재테크·절세','부업·수익'):
   if groups[c] and len(balanced)<90:balanced.append(groups[c].pop(0))
 return balanced,errors

def render(rows,errors):
 now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')
 counts={c:sum(x['category']==c for x in rows) for c in ('혜택·정책','재테크·절세','부업·수익')}
 cards=[]
 for x in rows:
  badge='🏛️ 공식' if x['official'] else '📰 교차확인 후보'
  rel=''.join(f'<a href="{html.escape(r["url"])}" target="_blank" rel="noopener">관련출처</a>' for r in x.get('related',[])[:4])
  cards.append(f'''<article class="card" data-cat="{html.escape(x['category'])}" data-q="{html.escape((x['title']+' '+x['summary']).lower())}">
<div class="badges"><span class="badge {'official' if x['official'] else ''}">{badge}</span><span class="badge">{html.escape(x['category'])}</span><span class="score">{x['score']}점</span></div>
<h2>{html.escape(x['title'])}</h2><p>{html.escape(x['summary'] or '원문에서 대상·조건·금액을 확인하세요.')}</p>
<div class="meta">{html.escape(x['source_label'])}{' · '+html.escape(x['amount']) if x['amount'] else ''}</div>
<div class="links"><a class="primary" href="{html.escape(x['url'])}" target="_blank" rel="noopener">원문 보기</a>{rel}</div></article>''')
 data=json.dumps({'generated_at':now,'counts':counts,'items':rows,'errors':errors},ensure_ascii=False,indent=2)
 (ROOT/'data.json').write_text(data,encoding='utf-8')
 return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>돈되는 소재 레이더</title><meta name="robots" content="noindex,nofollow"><style>
:root{{--bg:#0b0e13;--p:#121720;--line:#263041;--txt:#eef3fa;--muted:#8592a6}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,"Malgun Gothic",sans-serif}}.wrap{{max-width:1320px;margin:auto;padding:26px 20px 70px}}h1{{margin:0;font-size:28px}}.sub{{color:var(--muted);margin:7px 0 18px}}.stats,.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px}}.stat,.filter{{border:1px solid var(--line);background:var(--p);color:var(--txt);border-radius:10px;padding:9px 12px}}.filter{{cursor:pointer}}.filter.on{{background:#29446d}}#q{{min-width:250px;flex:1;background:#0f141c;border:1px solid var(--line);border-radius:10px;padding:10px;color:white}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.card{{background:var(--p);border:1px solid var(--line);border-radius:15px;padding:17px}}.badges{{display:flex;gap:6px;align-items:center}}.badge{{font-size:11px;border:1px solid #344156;border-radius:999px;padding:4px 7px;color:#b8c6d8}}.badge.official{{color:#ffe7a4;border-color:#76601f;background:#29230f}}.score{{margin-left:auto;color:#8cc2ff;font-size:12px}}h2{{font-size:17px;line-height:1.45;margin:11px 0 8px}}p{{font-size:13px;line-height:1.55;color:#c8d1dc;margin:0}}.meta{{font-size:11px;color:var(--muted);margin-top:10px}}.links{{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}}.links a{{font-size:12px;text-decoration:none;border:1px solid #38506f;padding:7px 9px;border-radius:8px;color:#d9e9ff}}.links .primary{{background:#183052}}.notice{{font-size:12px;color:#8290a2;margin:10px 0 17px}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}.wrap{{padding:18px 12px 50px}}}}
</style></head><body><main class="wrap"><h1>💰 돈되는 소재 레이더</h1><div class="sub">부업 · 재테크 · 지원사업만. 커뮤니티 잡담은 제외합니다.</div><div class="stats"><div class="stat">전체 <b>{len(rows)}</b></div><div class="stat">혜택·정책 <b>{counts['혜택·정책']}</b></div><div class="stat">재테크·절세 <b>{counts['재테크·절세']}</b></div><div class="stat">부업·수익 <b>{counts['부업·수익']}</b></div></div><div class="filters"><button class="filter on" data-cat="all">전체</button><button class="filter" data-cat="혜택·정책">혜택·정책</button><button class="filter" data-cat="재테크·절세">재테크·절세</button><button class="filter" data-cat="부업·수익">부업·수익</button><input id="q" placeholder="검색"></div><div class="notice">갱신 {now} · 공식 공고는 공식 원문, 뉴스 후보는 반드시 원문 확인 후 사용</div><section class="grid" id="grid">{''.join(cards)}</section></main><script>
let cat='all';const q=document.getElementById('q');function apply(){{const s=q.value.trim().toLowerCase();document.querySelectorAll('.card').forEach(x=>x.style.display=(cat==='all'||x.dataset.cat===cat)&&(!s||x.dataset.q.includes(s))?'':'none')}}document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('on'));b.classList.add('on');cat=b.dataset.cat;apply()}});q.oninput=apply;
</script></body></html>'''

def main():
 rows,errors=collect();
 if len(rows)<8:raise SystemExit(f'too few qualified rows: {len(rows)} errors={errors}')
 if sum(x['category']=='부업·수익' for x in rows)<2:raise SystemExit('too few side-income rows')
 if any(any(w in x['title'].lower() for w in BAD) for x in rows):raise SystemExit('junk title leaked')
 (ROOT/'index.html').write_text(render(rows,errors),encoding='utf-8')
 print('RADAR_BUILD_OK',len(rows),{c:sum(x['category']==c for x in rows) for c in ('혜택·정책','재테크·절세','부업·수익')},'errors',errors)
if __name__=='__main__':main()
