from __future__ import annotations
import datetime as dt
import html, json, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT=Path(__file__).parent
KST=dt.timezone(dt.timedelta(hours=9))
NOW=dt.datetime.now(dt.timezone.utc)
WINDOW_DAYS=14
CUTOFF=NOW-dt.timedelta(days=WINDOW_DAYS)
TOPICS=json.loads((ROOT/'topics.json').read_text(encoding='utf-8'))
LANES=('부업','재테크','혜택','SNS분석','리뷰어','AI','꿀팁','플랫폼')
LANE_LIMIT={k:7 for k in LANES}
MIN_SCORE=67
SOURCE_SCORES={
 '연합뉴스':22,'뉴스1':20,'뉴시스':20,'한국경제':18,'매일경제':18,'머니투데이':18,'이데일리':18,
 '서울경제':18,'아시아경제':17,'전자신문':18,'zdnet':18,'블로터':16,'비즈워치':16,'헤럴드경제':16,
 'kbs':18,'mbc':17,'sbs':17,'jtbc':16,'금융위원회':25,'금융감독원':25,'한국은행':25,'국세청':25,
 '기획재정부':25,'고용노동부':25,'중소벤처기업부':25,'정부24':25,'복지로':25,'youtube':25,'google':25,
 'openai':25,'anthropic':25,'microsoft':23,'meta':23,'네이버':23,'카카오':22,'삼성전자':22,'lg전자':22,'틱톡':21,'쿠팡':21,'reuters':22,'techcrunch':20,'the verge':20,'venturebeat':18,'engadget':18,'디지털데일리':17,'it조선':17,'테크m':16,'플래텀':16,'아이뉴스24':17,'뉴스핌':16,'아주경제':16,'데일리팝':14,'디지털투데이':16,'지디넷코리아':18,'cnet':16,'브랜드브리프':15,'매드타임스':14,'더피알':14,'뉴스와이어':12,'정책브리핑':23,'대한민국 정책브리핑':23,'고용24':24,'한국주택금융공사':24,'국민연금공단':24,'소상공인시장진흥공단':24,'chosunbiz':18,'중앙일보':17,'동아일보':17,'한국일보':17,'국민일보':16,'문화일보':16,'서울신문':16,'경향신문':17,'세계일보':15,'조선일보':16,'브릿지경제':14,'한국금융신문':16,'서울파이낸스':15,'데일리한국':14,'이코노미스트':16,'시사저널e':15,'samsung global newsroom':24,'youtube official blog':25,'google blog':25,'apple':24}
BLOCK=('싱글벙글','ㅋㅋ','남친','여친','연애','번호따','퇴사썰','알바썰','특징주','목표주가','투자의견','상한가','급등주','주식 추천','리딩방','수익 보장','원금 보장','무료 강의','사주','운세','로또','코인 추천','리뷰 알바','구매평 알바','리뷰 대행')
MONEY_RE=re.compile(r'(?<!\d)\d[\d,]*(?:\.\d+)?\s*(?:천|만|억)?\s*원|\d+(?:\.\d+)?\s*[%％]')
def fetch(url,timeout=12):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 TopicHunt/3.0'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def clean(s):
 s=html.unescape(s or '')
 return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',s)).strip()

def parse_date(s):
 try:
  from email.utils import parsedate_to_datetime
  d=parsedate_to_datetime(s)
  if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
  return d.astimezone(dt.timezone.utc)
 except Exception:return None

def text_of(node,names):
 for name in names:
  el=node.find(name)
  if el is None:el=node.find('{*}'+name)
  if el is not None and (el.text or '').strip():return el.text.strip()
 return ''

def source_of(node):
 el=node.find('source')
 if el is None:el=node.find('{*}source')
 return clean(el.text if el is not None else '')
def source_score(src):
 s=src.lower()
 return max((v for k,v in SOURCE_SCORES.items() if k.lower() in s),default=0)

def tokens(s):
 stop={'오늘','이번','관련','공개','변경','업데이트','기능','방법','지원','신청','수익','정보','서비스','플랫폼'}
 return {x for x in re.findall(r'[0-9a-zA-Z가-힣]{2,}',clean(s).lower()) if x not in stop and not x.isdigit()}

def allowed(topic,title,summary):
 text=(title+' '+summary).lower(); lane=topic['lane']
 if any(x.lower() in text for x in BLOCK):return False
 if not any(x.lower() in text for x in topic['must']):return False
 if not any(x.lower() in text for x in topic['signals']):return False
 if lane=='혜택' and not any(x in text for x in ('신청','접수','모집','지급','대상','마감','한도','캐시백')):return False
 if lane=='리뷰어' and (not any(x in text for x in ('모집','신청','선정','캠페인','제공')) or not any(x in text for x in ('리뷰','후기','제품','사용기','제공','콘텐츠','sns','서포터즈','앰배서더','크리에이터'))):return False
 if lane=='AI' and any(x in text for x in ('주가','특징주','투자의견','실적 전망','증권가')):return False
 if lane=='SNS분석' and not any(x in text for x in ('분석','인사이트','지표','도달','알고리즘','추천','집계','기준','방식','개편','변경')):return False
 if lane=='꿀팁' and not any(x in text for x in ('기능','설정','무료','방법','신청','이용','제공','업데이트')):return False
 if lane=='부업' and any(x in text for x in ('기업 실적','매출 전망','주가','증시','직원 부업 허용')):return False
 return True

def score(topic,title,summary,source,published):
 age=max(0,(NOW-published).total_seconds()/3600)
 fresh=28 if age<=6 else 24 if age<=12 else 19
 text=(title+' '+summary).lower(); sc=25+fresh+source_score(source)
 sc+=min(12,3*sum(x in text for x in ('신청','모집','출시','오픈','무료','정산','수수료','한도','마감','업데이트')))
 if MONEY_RE.search(text):sc+=8
 if topic['lane']=='SNS분석' and any(x in text for x in ('알고리즘','인사이트','도달','추천','집계','기준','방식','개편','변경')):sc+=10
 if topic['lane']=='부업' and any(x in text for x in ('수익화','수익 배분','제휴','수수료','정산','쇼핑','파트너 프로그램')):sc+=8
 if topic['lane']=='리뷰어' and any(x in text for x in ('모집','신청','선정')):sc+=12
 if topic['lane']=='꿀팁' and any(x in text for x in ('기능','설정','무료','업데이트','방법')):sc+=8
 if topic['lane']=='플랫폼' and any(x in text for x in ('정책','기능','수익화','변경','크리에이터')):sc+=8
 return min(99,sc)
def collect_page(topic):
 try:raw=fetch(topic["direct_page"]).decode("utf-8","ignore")
 except Exception as e:return [],f"{topic['id']}: {type(e).__name__}: {str(e)[:80]}"
 text=clean(raw); months="January|February|March|April|May|June|July|August|September|October|November|December"
 pat=re.compile(rf"({months})\s+(\d{{1,2}}),\s+(\d{{4}})")
 for m in pat.finditer(text):
  try:published=dt.datetime.strptime(m.group(0),"%B %d, %Y").replace(tzinfo=dt.timezone.utc)
  except Exception:continue
  if published<CUTOFF:continue
  chunk=text[m.end():m.end()+700]; low=chunk.lower()
  if topic.get("keywords") and not any(k.lower() in chunk.lower() for k in topic.get("keywords",[])):continue
  sentence=re.split(r"(?<=[.!?])\s+",chunk)[0][:180].strip()
  if len(sentence)<20:sentence=f"YouTube Analytics official update - {m.group(0)}"
  return [{"topic_id":topic["id"],"lane":topic["lane"],"label":topic["label"],"title":sentence,"summary":chunk[:500],"url":topic["direct_page"],"source":topic["label"],"published_at":published.isoformat(),"score":92,"tokens":sorted(tokens(sentence)),"money":[]}],None
 return [],None

def collect_direct(topic):
 try:root=ET.fromstring(fetch(topic["direct_url"]))
 except Exception as e:return [],f"{topic['id']}: {type(e).__name__}: {str(e)[:80]}"
 out=[]; nodes=list(root.findall(".//item"))+list(root.findall(".//{*}entry"))
 for node in nodes:
  title=clean(text_of(node,("title",))); summary=clean(text_of(node,("description","summary","content")))
  link=text_of(node,("link",)); le=node.find("link"); le=le if le is not None else node.find("{*}link")
  if not link and le is not None:link=le.attrib.get("href","")
  published=parse_date(text_of(node,("pubDate","published","updated")))
  if not title or not link or published is None or published<CUTOFF:continue
  text=(title+" "+summary).lower()
  if not any(k.lower() in text for k in topic.get("keywords",[])):continue
  if any(k.lower() in title.lower() for k in topic.get("title_block",[])):continue
  title_req=topic.get("require_title_any",[])
  if title_req and not any(k.lower() in title.lower() for k in title_req):continue
  req=topic.get("require_any",[])
  if req and not any(k.lower() in text for k in req):continue
  age=max(0,(NOW-published).total_seconds()/3600); sc=94 if age<=24 else 88 if age<=72 else 82
  out.append({"topic_id":topic["id"],"lane":topic["lane"],"label":topic["label"],"title":title,"summary":summary,"url":link,"source":topic["label"],"published_at":published.isoformat(),"score":sc,"tokens":sorted(tokens(title)),"money":MONEY_RE.findall(title+" "+summary)[:3]})
 return out,None

def collect_topic(topic):
 if topic.get('direct_page'):return collect_page(topic)
 if topic.get('direct_url'):return collect_direct(topic)
 q=topic['query']+f' when:{WINDOW_DAYS}d'
 url='https://news.google.com/rss/search?q='+urllib.parse.quote(q)+'&hl=ko&gl=KR&ceid=KR:ko'
 try:root=ET.fromstring(fetch(url))
 except Exception as e:return [],f"{topic['id']}: {type(e).__name__}: {str(e)[:80]}"
 out=[]
 for node in root.findall('.//item'):
  raw=clean(text_of(node,('title',))); summary=clean(text_of(node,('description','summary')))
  link=text_of(node,('link',)); src=source_of(node); published=parse_date(text_of(node,('pubDate','published','updated')))
  if not raw or not link or not src or source_score(src)<10 or published is None or published<CUTOFF:continue
  title=raw
  for sep in (' - ',' | '):
   suffix=sep+src
   if title.lower().endswith(suffix.lower()):title=title[:-len(suffix)].strip()
  if not allowed(topic,title,summary):continue
  sc=score(topic,title,summary,src,published)
  if sc<MIN_SCORE:continue
  out.append({'topic_id':topic['id'],'lane':topic['lane'],'label':topic['label'],'title':title,'summary':summary,
              'url':link,'source':src,'published_at':published.isoformat(),'score':sc,'tokens':sorted(tokens(title)),
              'money':MONEY_RE.findall(title+' '+summary)[:3]})
 return out,None

def similarity(a,b):
 A,B=set(a['tokens']),set(b['tokens'])
 if not A or not B:return 0
 hit=len(A&B)
 return hit/max(1,len(A|B)) if hit>=2 else 0

def dedupe(rows):
 kept=[]
 for x in sorted(rows,key=lambda z:(z['score'],z['published_at']),reverse=True):
  dup=None
  for y in kept:
   sim=similarity(x,y)
   same_topic=x['topic_id']==y['topic_id']
   nums_x=set(re.findall(r'\d+(?:\.\d+)?',x['title'])); nums_y=set(re.findall(r'\d+(?:\.\d+)?',y['title']))
   finance_dup=same_topic and x['topic_id'] in {'loan','deposit','tax','mortgage_policy','bank_product'} and bool(nums_x & nums_y) and len(set(x['tokens']) & set(y['tokens']))>=1
   tx=(x['title']+' '+x.get('summary','')).lower(); ty=(y['title']+' '+y.get('summary','')).lower()
   sns_youtube_dup=(x['lane']=='SNS분석' and y['lane']=='SNS분석' and '유튜브' in tx and '유튜브' in ty and any(k in tx for k in ('조회수','집계','기준')) and any(k in ty for k in ('조회수','집계','기준')))
   if sim>=.46 or (same_topic and sim>=.32) or finance_dup or sns_youtube_dup:
    dup=y; break
  if dup:
   dup.setdefault('related',[]).append({'name':x['source'],'title':x['title'],'url':x['url']})
   continue
  x['related']=[];kept.append(x)
 return kept
def seen_before(row,seen):
 for old in seen:
  if old.get("topic_id")!=row.get("topic_id"):continue
  A=set(row.get("tokens") or tokens(row.get("title","")));B=set(old.get("tokens",[]))
  if not A or not B:continue
  hit=len(A&B); sim=hit/max(1,len(A|B))
  try:old_date=dt.date.fromisoformat(old.get("date","1900-01-01"))
  except Exception:old_date=dt.date(1900,1,1)
  recent=(dt.datetime.now(KST).date()-old_date).days<=3
  nums_a=set(re.findall(r"\d+(?:\.\d+)?",row.get("title",""))); nums_b=set(re.findall(r"\d+(?:\.\d+)?",old.get("title","")))
  finance_repeat=row.get("topic_id") in {"loan","deposit","tax"} and recent and bool(nums_a & nums_b) and hit>=1
  if sim>=.32 or hit>=3 or (recent and hit>=2) or finance_repeat:return True
 return False

def final_items(rows):
 rows=dedupe(rows); topic_count=Counter(); lane_count=Counter(); out=[]
 for x in sorted(rows,key=lambda z:(z['score'],z['published_at']),reverse=True):
  if topic_count[x['topic_id']]>=3 or lane_count[x['lane']]>=LANE_LIMIT[x['lane']]:continue
  topic_count[x['topic_id']]+=1;lane_count[x['lane']]+=1
  related=x.pop('related',[]); srcs=[{'name':x['source'],'title':x['title'],'url':x['url']}]
  seen={x['source']}
  for r in related:
   if r['name'] not in seen:srcs.append(r);seen.add(r['name'])
  status='NOW' if x['score']>=88 else 'PICK' if x['score']>=78 else 'WATCH'
  money=[]
  for m in x.pop('money',[]):
   if m not in money:money.append(m)
  out.append({'id':x['topic_id']+'-'+re.sub(r'[^0-9a-z가-힣]','',x['title'].lower())[:42],
   'topic_id':x['topic_id'],'lane':x['lane'],'label':x['label'],'status':status,'score':x['score'],
   'headline':x['title'],'why_now':why_text(x['lane']),'angle':next(t['angle'] for t in TOPICS if t['id']==x['topic_id']),
   'check_first':next(t['check'] for t in TOPICS if t['id']==x['topic_id']),'money_signal':money[:3],
   'published_at':x['published_at'],'source_count':len(srcs),'sources':srcs[:4]})
 return out

def why_text(lane):
 return {'부업':'실제 수익 구조나 정산 조건에 연결되는 변화.', '재테크':'금리·세제·상품 조건이 실제 돈 차이로 이어지는 변화.',
 '혜택':'대상·금액·기한을 놓치면 못 받는 정보.', 'SNS분석':'계정 지표·알고리즘 변화라 운영 방식에 바로 반영 가능.',
 '리뷰어':'신청·선정·제공 조건이 있는 실제 참여 기회.', 'AI':'새 기능·도구를 업무·콘텐츠 제작에 바로 시험할 가치가 있음.',
 '꿀팁':'무료 기능·설정·공식 서비스처럼 바로 적용 가능한 정보.', '플랫폼':'플랫폼 정책·기능 변화가 운영 방식에 영향을 줌.'}[lane]
def render(data):
 items=data['items'];counts=data['counts'];now=sum(x['status']=='NOW' for x in items)
 cards=[]
 for x in items:
  money=' · '.join(x['money_signal']) if x['money_signal'] else '핵심 수치는 원문 확인'
  links=''.join(f'<a href="{html.escape(s["url"])}" target="_blank">{html.escape(s["name"])}</a>' for s in x['sources'])
  q=html.escape((x['headline']+' '+x['lane']+' '+x['label']+' '+x['angle']).lower())
  cards.append(f'''<article class="card" data-lane="{x['lane']}" data-status="{x['status']}" data-q="{q}"><div class="top"><div><span class="status {x['status'].lower()}">{x['status']}</span><span>{x['lane']}</span><span>{x['label']}</span></div><b>{x['score']}</b></div><h2>{html.escape(x['headline'])}</h2><div class="money">{html.escape(money)}</div><dl><dt>왜 지금</dt><dd>{html.escape(x['why_now'])}</dd><dt>콘텐츠 각도</dt><dd>{html.escape(x['angle'])}</dd><dt>먼저 확인</dt><dd>{html.escape(x['check_first'])}</dd></dl><div class="foot"><small>근거 {x['source_count']}개</small><div>{links}</div></div></article>''')
 filters=''.join(f'<button class="filter" data-lane="{l}">{l}<b>{counts.get(l,0)}</b></button>' for l in LANES)
 kpis=''.join(f'<div class="kpi"><span>{l}</span><b>{counts.get(l,0)}</b></div>' for l in ('부업','SNS분석','리뷰어','AI','꿀팁'))
 return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>TOPIC HUNT</title><style>
:root{{--bg:#07090d;--panel:#10151d;--line:#222c3a;--txt:#f4f7fb;--muted:#8390a2}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 20% -10%,#1b2940 0,transparent 32%),var(--bg);color:var(--txt);font-family:system-ui,-apple-system,"Pretendard","Malgun Gothic",sans-serif}}.wrap{{max-width:1500px;margin:auto;padding:32px 20px 70px}}.eyebrow{{font-size:11px;letter-spacing:.18em;color:#74849a;font-weight:800}}h1{{font-size:42px;margin:8px 0 8px;letter-spacing:-.04em}}.sub{{color:#9aa6b7;font-size:14px}}.hero{{display:flex;justify-content:space-between;align-items:end;gap:20px}}.updated{{font-size:12px;color:#69768a;white-space:nowrap}}.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin:22px 0 14px}}.kpi{{background:#0d1219;border:1px solid var(--line);border-radius:13px;padding:13px}}.kpi span{{display:block;color:#7c899c;font-size:11px}}.kpi b{{font-size:24px}}.bar{{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0 18px}}button,#search{{border:1px solid var(--line);background:#0d1219;color:#aeb8c7;border-radius:10px;padding:9px 10px}}button{{cursor:pointer}}button.on{{background:#203049;color:#fff}}button b{{margin-left:6px;color:#65748a}}#search{{margin-left:auto;min-width:260px;outline:none}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.card{{background:linear-gradient(180deg,#111720,#0d1219);border:1px solid var(--line);border-radius:15px;padding:16px}}.top{{display:flex;justify-content:space-between;align-items:center;gap:10px}}.top span{{font-size:10px;border:1px solid #2e3949;border-radius:999px;padding:4px 7px;margin-right:4px;color:#9eabbd}}.top b{{color:#75849a;font-size:17px}}.status.now{{color:#ffc477;border-color:#6d4d29}}.status.pick{{color:#a8caff;border-color:#355073}}h2{{font-size:17px;line-height:1.48;margin:12px 0 9px}}.money{{display:inline-block;font-size:11px;color:#93d7b5;background:#0d1c18;border:1px solid #19362e;padding:5px 7px;border-radius:8px}}dl{{margin:12px 0 0;border-top:1px solid #1d2632;padding-top:10px}}dt{{font-size:10px;color:#68778b;font-weight:800;margin-top:8px}}dd{{margin:3px 0 0;color:#bdc6d2;font-size:12.5px;line-height:1.5}}.foot{{display:flex;justify-content:space-between;gap:8px;border-top:1px solid #1d2632;margin-top:12px;padding-top:10px}}small{{color:#68778b}}.foot a{{font-size:10px;color:#8fb8ef;text-decoration:none;border:1px solid #2b4059;border-radius:7px;padding:4px 6px;margin-left:4px}}.rules{{margin-top:20px;color:#617084;font-size:11px}}.empty{{display:none;text-align:center;color:#68778b;padding:60px}}@media(max-width:1050px){{.grid{{grid-template-columns:repeat(2,1fr)}}.kpis{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:720px){{.wrap{{padding:22px 12px 50px}}.hero{{display:block}}h1{{font-size:34px}}.updated{{margin-top:8px}}.grid{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(2,1fr)}}#search{{width:100%;margin-left:0}}}}</style></head><body><main class="wrap"><section class="hero"><div><div class="eyebrow">DAILY EDITORIAL RADAR</div><h1>TOPIC HUNT</h1><div class="sub">매일 새로 수집. 돈정보·SNS계정분석·리뷰어·AI·꿀팁까지 오늘 쓸 소재만.</div></div><div class="updated">최근 14일 새 후보 · {data['generated_at']}</div></section><section class="kpis">{kpis}</section><div class="bar"><button class="filter on" data-lane="all">전체<b>{len(items)}</b></button><button class="filter" data-lane="NOW">NOW<b>{now}</b></button>{filters}<input id="search" placeholder="SNS·AI·리뷰어·부업·혜택 검색"></div><section class="grid" id="grid">{''.join(cards)}</section><div id="empty" class="empty">오늘 품질 기준을 통과한 소재가 없다.</div><div class="rules">매일 09:40 KST 전날 화면 전부 폐기 → 최근 14일 소스를 다시 훑고 지난 7일에 보여준 사건은 제외 → 같은 사건 1개로 병합. 잡담·주가 찌라시·리뷰알바·수익보장·오래된 기사 누적 금지.</div></main><script>let lane='all',q=document.getElementById('search');function apply(){{let s=q.value.trim().toLowerCase(),n=0;document.querySelectorAll('.card').forEach(c=>{{let ok=(lane==='all'||c.dataset.lane===lane||(lane==='NOW'&&c.dataset.status==='NOW'))&&(!s||c.dataset.q.includes(s));c.style.display=ok?'':'none';if(ok)n++}});document.getElementById('empty').style.display=n?'none':'block'}}document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('on'));b.classList.add('on');lane=b.dataset.lane;apply()}});q.oninput=apply;</script></body></html>'''
def main():
 rows=[];errors=[];raw_counts={}
 with ThreadPoolExecutor(max_workers=10) as pool:
  futures={pool.submit(collect_topic,t):t for t in TOPICS}
  for f in as_completed(futures):
   t=futures[f]
   try:r,e=f.result()
   except Exception as ex:r,e=[],f"{t['id']}: {type(ex).__name__}: {str(ex)[:80]}"
   raw_counts[t['id']]=len(r);rows.extend(r)
   if e:errors.append(e)
 seen_path=ROOT/'seen.json'
 try:seen=json.loads(seen_path.read_text(encoding='utf-8'))
 except Exception:seen=[]
 rows=[r for r in rows if not seen_before(r,seen)]
 items=final_items(rows)
 today=dt.datetime.now(KST).date()
 for x in items:seen.append({'topic_id':x['topic_id'],'title':x['headline'],'tokens':sorted(tokens(x['headline'])),'date':today.isoformat()})
 keep_after=(today-dt.timedelta(days=7)).isoformat()
 seen=[x for x in seen if x.get('date','9999-99-99')>=keep_after]
 seen_path.write_text(json.dumps(seen,ensure_ascii=False,indent=2),encoding='utf-8')
 counts={l:sum(x['lane']==l for x in items) for l in LANES}
 data={'generated_at':dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),'counts':counts,'items':items,
       'meta':{'window_days':WINDOW_DAYS,'refresh_policy':'daily_replace_no_repeat_7d','raw_articles':len(rows),'shown':len(items),'topic_raw_counts':raw_counts,'errors':errors}}
 (ROOT/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (ROOT/'index.html').write_text(render(data),encoding='utf-8')
 print('TOPIC_HUNT_OK',counts,data['meta'])
 for x in items:print(f"[{x['lane']}] {x['status']} {x['score']} {x['headline']} / {x['source_count']} sources")

if __name__=='__main__':main()
