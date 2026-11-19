"""Decontare generală pentru orice piață Superbet (goluri, reprize, intervale, totaluri pe echipe, linii asiatice,
handicapuri, cornere, combinații 1X2/Șansă dublă & goluri, Bet Builder pe goluri/cornere), din scor, pauză și cornere.

Numele echipelor din textul Superbet se înlocuiesc cu {H} / {A} (``canon``), ca piața să fie aceeași de la un meci
la altul. Echipele se află din piața „Egal - Pariul se rambursează (DNB)” comparată cu „Final” (``teams``)."""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, Iterable, Optional, Tuple

W=(1,0); L=(0,0); P=(0,1)
def b(x): return None if x is None else (W if x else L)
def norm(s): return re.sub(r'\s+',' ',s.replace('ş','ș').replace('ţ','ț').replace('Ş','Ș').strip())

def stat(m,kind,per,side):
    """kind g/c/k, per FT/1/2, side T/H/A"""
    if kind=='g': src={'FT':(m['fh'],m['fa']),'1':(m['hh'],m['ha'])}
    elif kind=='c': src={'FT':(m['ch'],m['ca']),'1':(m['chh'],m['cha'])}
    else: src={'FT':(m['kh'],m['ka'])}
    if per=='2':
        a=src.get('FT'); b_=src.get('1')
        if not a or not b_ or None in a or None in b_: return None
        v=(a[0]-b_[0],a[1]-b_[1])
    else:
        v=src.get(per)
        if not v or None in v: return None
    if side=='H': return v[0]
    if side=='A': return v[1]
    if side=='P': return v
    return v[0]+v[1]

PER={'':'FT','Prima repriză - ':'1','A doua repriză - ':'2'}
KIND={'goluri':'g','cornere':'c','cartonașe':'k'}

def ou(oc,val):
    m_=re.fullmatch(r'(Peste|Sub) (\d+(?:\.\d+)?)',oc)
    if not m_ or val is None: return None
    l=float(m_.group(2)); over=m_.group(1)=='Peste'
    frac=round(l-int(l),2)
    if frac in (0.25,0.75):  # asian quarter
        a=ou_line(over,l-0.25,val); c=ou_line(over,l+0.25,val)
        return ((a[0]+c[0])/2,(a[1]+c[1])/2)
    return ou_line(over,l,val)
def ou_line(over,l,val):
    if val==l: return P
    return W if (val>l)==over else L
def rng(oc,v):
    if v is None: return None
    oc=oc.strip()
    m_=re.fullmatch(r'(\d+)-(\d+)',oc)
    if m_: return b(int(m_.group(1))<=v<=int(m_.group(2)))
    m_=re.fullmatch(r'(\d+)\+',oc)
    if m_: return b(v>=int(m_.group(1)))
    m_=re.fullmatch(r'<(\d+)',oc)
    if m_: return b(v<int(m_.group(1)))
    if oc.isdigit(): return b(v==int(oc))
    return None
def res3(h,a): return '1' if h>a else 'X' if h==a else '2'
def x12(oc,h,a):
    r=res3(h,a)
    if oc in ('1','X','2'): return r==oc
    if oc in ('1X','X2','12'): return r in oc
    if oc=='{H}': return r=='1'
    if oc=='{A}': return r=='2'
    if oc in('Egal','Egalitate'): return r=='X'
    return None
def dn(x): return None if x is None else x

def pred(t,m):
    """BB component / sub-proposition -> True/False/None"""
    t=norm(t)
    g=lambda per,side='T': stat(m,'g',per,side)
    mm=re.fullmatch(r'(Peste|Sub) (\d+\.5) (goluri|cornere|cartonașe)( în prima repriză| în a doua repriză)?',t)
    if mm:
        per={'':'FT',' în prima repriză':'1',' în a doua repriză':'2'}[mm.group(4) or '']
        v=stat(m,KIND[mm.group(3)],per,'T'); r=ou(f'{mm.group(1)} {mm.group(2)}',v); return None if r is None else r==W
    mm=re.fullmatch(r'\{(H|A)\} (peste|sub) (\d+\.5) (goluri|cornere|cartonașe)',t)
    if mm:
        v=stat(m,KIND[mm.group(4)],'FT',mm.group(1)); r=ou(f'{mm.group(2).capitalize()} {mm.group(3)}',v); return None if r is None else r==W
    if t=='Ambele echipe marchează': return m['fh']>0 and m['fa']>0
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )?(.*)',t); per=PER[mm.group(1) or '']; rest=mm.group(2)
    v=stat(m,'g',per,'P')
    if v is not None:
        r=res3(*v)
        d={'{H} câștigă':r=='1','{A} câștigă':r=='2','{H} câștigă sau egal':r!='2','Egal sau {A} câștigă':r!='1','{H} sau {A} câștigă':r!='X','Egalitate':r=='X','Egal':r=='X'}
        if rest in d: return d[rest]
    mm=re.fullmatch(r'Fiecare echipă va (avea|primi) peste (\d+\.5) (cornere|cartonașe)',t)
    if mm:
        v=stat(m,KIND[mm.group(3)],'FT','P'); l=float(mm.group(2))
        return None if v is None else (v[0]>l and v[1]>l)
    mm=re.fullmatch(r'\{(H|A)\} va avea cele mai multe (cornere|cartonașe)',t)
    if mm:
        v=stat(m,KIND[mm.group(2)],'FT','P')
        if v is None: return None
        return v[0]>v[1] if mm.group(1)=='H' else v[1]>v[0]
    h1=stat(m,'g','1','P'); h2=stat(m,'g','2','P')
    if h1 is None: return None
    i=0
    mm=re.fullmatch(r'\{(H|A)\} (câștigă ambele reprize|câștigă oricare din reprize|câștigă oricare dintre reprize|marchează în ambele reprize|marchează peste 0.5 goluri în prima repriză|marchează peste 0.5 goluri în a 2-a repriză)',t)
    if mm:
        s=0 if mm.group(1)=='H' else 1; o=1-s; ph=mm.group(2)
        w1=h1[s]>h1[o]; w2=h2[s]>h2[o]
        if ph=='câștigă ambele reprize': return w1 and w2
        if ph.startswith('câștigă oricare'): return w1 or w2
        if ph=='marchează în ambele reprize': return h1[s]>0 and h2[s]>0
        if ph.endswith('prima repriză'): return h1[s]>0
        return h2[s]>0
    if t=='În a doua repriză se vor înscrie cele mai multe goluri': return sum(h2)>sum(h1)
    if t=='Minim o repriză se termină la egalitate': return h1[0]==h1[1] or h2[0]==h2[1]
    if t=='Gol marcat în ambele reprize': return sum(h1)>0 and sum(h2)>0
    return None

def settle(mn,oc,m):
    """returns (win_share, refund_share) or None"""
    mn=norm(mn); oc=norm(oc)
    if ';' in mn:
        if oc not in ('Da',''): 
            if oc=='Nu': pass
        ps=[pred(x,m) for x in mn.split('; ')]
        if None in ps: return None
        v=all(ps)
        return b(v if oc!='Nu' else not v)
    G=lambda per,side='T': stat(m,'g',per,side)
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )?Total (goluri|cornere|cartonașe)(?: asiatice)?(?: \{(H|A)\})?',mn)
    if mm:
        return ou(oc,stat(m,KIND[mm.group(2)],PER[mm.group(1) or ''],mm.group(3) or 'T'))
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )?Total (goluri|cornere) impar/par(?: \{(H|A)\})?',mn)
    if mm:
        v=stat(m,KIND[mm.group(2)],PER[mm.group(1) or ''],mm.group(3) or 'T')
        if v is None: return None
        return b((v%2==1) if oc=='Impar' else (v%2==0)) if oc in('Impar','Par') else None
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )?(Interval goluri|Număr exact de goluri|Interval cornere)(?: \{(H|A)\})?',mn)
    if mm:
        k='c' if 'cornere' in mm.group(2) else 'g'
        return rng(oc,stat(m,k,PER[mm.group(1) or ''],mm.group(3) or 'T'))
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )?(Final|1X2|Șansă dublă|Egal - Pariul se rambursează \(DNB\)|Ambele echipe marchează \(GG\)|Scor corect|Handicap european|Handicap|Handicap asiatic|Cornere 1X2|Golul 1)',mn)
    if mm:
        per=PER[mm.group(1) or '']; k=mm.group(2)
        v=stat(m,'c' if k=='Cornere 1X2' else 'g',per,'P')
        if v is None: return None
        h,a=v
        if k in('Final','1X2','Șansă dublă','Cornere 1X2'): return b(x12(oc,h,a)) if x12(oc,h,a) is not None else None
        if k.startswith('Egal'):
            if h==a: return P
            return b((oc=='{H}' and h>a) or (oc=='{A}' and a>h))
        if k.startswith('Ambele'): return b((h>0 and a>0)==(oc=='Da'))
        if k=='Scor corect':
            q=re.fullmatch(r'(\d+):(\d+)',oc); return b((h,a)==(int(q.group(1)),int(q.group(2)))) if q else None
        if k=='Handicap european':
            q=re.fullmatch(r'(\{H\}|\{A\}|Egalitate|Egal) \((\d+):(\d+)\)',oc)
            if not q: return None
            hh=h+int(q.group(2)); aa=a+int(q.group(3)); r=res3(hh,aa)
            return b(r==('1' if q.group(1)=='{H}' else '2' if q.group(1)=='{A}' else 'X'))
        if k in('Handicap','Handicap asiatic'):
            q=re.fullmatch(r'(\{H\}|\{A\}) \(([+-]?\d+(?:\.\d+)?)\)',oc)
            if not q: return None
            l=float(q.group(2)); d=(h-a) if q.group(1)=='{H}' else (a-h)
            # bet team with handicap l: wins if d+l>0
            def one(x): return P if d+x==0 else (W if d+x>0 else L)
            if round(abs(l)%0.5,2)==0.25:
                a1=one(l-0.25); a2=one(l+0.25); return ((a1[0]+a2[0])/2,(a1[1]+a2[1])/2)
            return one(l)
        if k=='Golul 1':
            if oc=='Nicio echipă': return b(h+a==0)
            if h>0 and a>0: return None
            if h+a==0: return L
            return b((oc=='{H}' and h>0) or (oc=='{A}' and a>0))
    mm=re.fullmatch(r'(Prima repriză - |A doua repriză - )Marchează \{(H|A)\}',mn)
    if mm:
        v=G(PER[mm.group(1)],mm.group(2)); return None if v is None else b((v>0)==(oc=='Da'))
    mm=re.fullmatch(r'Fiecare echipă va (avea|primi) peste X (cornere|cartonașe)',mn)
    if mm:
        q=re.fullmatch(r'Peste (\d+\.5) - (Da|Nu)',oc)
        if not q: return None
        r=pred(f'Fiecare echipă va {mm.group(1)} peste {q.group(1)} {mm.group(2)}',m)
        return None if r is None else b(r==(q.group(2)=='Da'))
    h1=G('1','P'); h2=G('2','P'); fh,fa=m['fh'],m['fa']; T=fh+fa
    if h1 is None: return None
    yn={'Fiecare echipă marchează 2+':fh>=2 and fa>=2,'GG & Peste 2.5 goluri':fh>0 and fa>0 and T>2,'GG & Peste 3.5 goluri':fh>0 and fa>0 and T>3,
        'GG sau Peste 2.5 goluri':(fh>0 and fa>0) or T>2,'GG sau Peste 3.5 goluri':(fh>0 and fa>0) or T>3,'GG sau Egalitate în meci':(fh>0 and fa>0) or fh==fa,
        'GG sau Câștigă {H}':(fh>0 and fa>0) or fh>fa,'GG sau Câștigă {A}':(fh>0 and fa>0) or fa>fh,'Gol marcat în ambele reprize':sum(h1)>0 and sum(h2)>0}
    if mn in yn:
        return b(yn[mn]) if oc=='Da' else b(not yn[mn]) if oc=='Nu' else None
    mm=re.fullmatch(r'(Repriza cu cele mai multe goluri|Interval goluri în fiecare repriză)(?: \{(H|A)\})?',mn)
    if mm:
        s=mm.group(2); f=lambda v:v[0] if s=='H' else v[1] if s=='A' else v[0]+v[1]
        x1,x2=f(h1),f(h2)
        if mm.group(1).startswith('Repriza'):
            return b({'Repriza 1':x1>x2,'Repriza 2':x2>x1,'Egalitate':x1==x2}[oc]) if oc in('Repriza 1','Repriza 2','Egalitate') else None
        a=rng(oc,x1); c=rng(oc,x2); return None if a is None else b(a==W and c==W)
    mm=re.fullmatch(r'Total goluri prima repriză & Total goluri( a doua repriză)?(?: \{(H|A)\})?',mn)
    if mm:
        s=mm.group(2); f=lambda v:v[0] if s=='H' else v[1] if s=='A' else v[0]+v[1]
        p=oc.split(' & ')
        if len(p)!=2: return None
        x=ou(p[0],f(h1)); y=ou(p[1],f(h2) if mm.group(1) else f(h1)+f(h2))
        return None if x is None or y is None else b(x==W and y==W)
    if mn=='Total goluri prima sau a doua repriză':
        p=oc.split(' sau ')
        x=ou(p[0],sum(h1)); y=ou(p[1],sum(h2)); return None if x is None or y is None else b(x==W or y==W)
    if mn=='Total goluri & GG':
        p=oc.split(' & '); x=ou(p[0],T)
        return None if x is None else b(x==W and ((fh>0 and fa>0)==(p[1]=='Da')))
    mm=re.fullmatch(r'(1X2|Șansă dublă) & (Total goluri(?: \{(H|A)\})? \((\d\.5)\)|Interval goluri|GG|Gol în ambele reprize)',mn)
    if mm:
        p=oc.split(' & ')
        if len(p)!=2: return None
        x=x12(p[0],fh,fa)
        if x is None: return None
        k=mm.group(2)
        if k.startswith('Total'):
            s=mm.group(3); v=fh if s=='H' else fa if s=='A' else T; y=ou(p[1],v); y=None if y is None else y==W
        elif k=='Interval goluri': y=rng(p[1],T); y=None if y is None else y==W
        elif k=='GG': y=(fh>0 and fa>0)==(p[1]=='Da')
        else: y=(sum(h1)>0 and sum(h2)>0)==(p[1]=='Da')
        return None if y is None else b(x and y)
    return None


DNB = "Egal - Pariul se rambursează (DNB)"


def teams(prices: Dict[Tuple[str, str], float]) -> Optional[Tuple[str, str]]:
    """(gazde, oaspeți) cum le scrie Superbet, din DNB + Final: favoritul la DNB e favoritul la Final."""
    fin = {o: p for (mn, o), p in prices.items() if mn == "Final"}
    dnb = {o: p for (mn, o), p in prices.items() if mn == DNB}
    if len(dnb) != 2 or "1" not in fin or "2" not in fin or fin["1"] == fin["2"]:
        return None
    (t1, _), (t2, _) = sorted(dnb.items(), key=lambda x: x[1])
    return (t1, t2) if fin["1"] < fin["2"] else (t2, t1)


def canon(s: str, t: Optional[Tuple[str, str]]) -> str:
    if not t:
        return s
    for name, tok in sorted([(t[0], "{H}"), (t[1], "{A}")], key=lambda x: -len(x[0])):
        if name:
            s = s.replace(name, tok)
    return s


def match_dict(r: Any) -> Dict[str, Any]:
    g = (lambda k: r[k]) if not isinstance(r, dict) else r.get
    return {"fh": g("ft_home"), "fa": g("ft_away"), "hh": g("ht_home"), "ha": g("ht_away"), "ch": g("corners_home"),
            "ca": g("corners_away"), "chh": g("corners_ht_home"), "cha": g("corners_ht_away"), "kh": None, "ka": None}


def result(mn: str, oc: str, m: Dict[str, Any]) -> Optional[str]:
    """won / lost / void pentru o piață canonică ({H}/{A}); None dacă nu se poate (date lipsă, jumătăți de linie)."""
    if m.get("fh") is None:
        return None
    try:
        r = settle(mn, oc, m)
    except Exception:  # noqa: BLE001 — o piață necunoscută nu se decontează
        return None
    if r is None:
        return None
    if r == W:
        return "won"
    if r == L:
        return "lost"
    if r == P:
        return "void"
    return None  # jumătate câștigat / jumătate rambursat (linii asiatice .25/.75): nu le folosim


def key_of(mn: str, oc: str) -> str:
    return "SB:" + norm(mn) + "|" + norm(oc)


def split_key(key: str) -> Tuple[str, str]:
    mn, _, oc = key[3:].partition("|")
    return mn, oc


def label(key: str) -> str:
    mn, oc = split_key(key)
    txt = f"{mn}: {oc}" if oc not in ("", mn) else mn
    return txt.replace("{H}", "Gazde").replace("{A}", "Oaspeți")


def settle_sb_legs(conn: sqlite3.Connection) -> int:
    """Selecțiile de bilet din piețele găsite de Robot (market 'sb|0', selecția = cheia canonică)."""
    from betpredict.ingest.corners import ensure as ensure_corners
    from betpredict.ingest.normalize import VOID_STATUSES

    ensure_corners(conn)  # coloanele cu cornerele de la pauză
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    n = 0
    for l in cur.execute(
            """SELECT tl.rowid rid, tl.selection, m.status, m.ft_home, m.ft_away, m.ht_home, m.ht_away, m.corners_home, m.corners_away,
                      m.corners_ht_home, m.corners_ht_away
               FROM ticket_leg tl JOIN match m ON m.id = tl.match_id WHERE tl.market='sb|0' AND tl.result IS NULL""").fetchall():
        if l["status"] in VOID_STATUSES:
            res = "void"
        elif (l["status"] or "").lower() not in {"finished", "ft", "ended", "aet", "pen"}:
            continue
        else:
            res = result(*split_key(l["selection"]), match_dict(l))
            if res is None:
                continue
        conn.execute("UPDATE ticket_leg SET result=? WHERE rowid=?", (res, l["rid"]))
        n += 1
    return n
