import pickle,sqlite3,math,numpy as np,sys
sys.path.insert(0,'/workspace/bp-analysis')
from betpredict.model.dc import score_matrix
from betpredict.model.calib import shin
d=pickle.load(open('wf45.pkl','rb'));pos={int(i):j for j,i in enumerate(d['ids'])}
c=sqlite3.connect('file:fd.db?mode=ro',uri=True)
rows=c.execute("select match_id,season,fthg,ftag,avgc_h,avgc_d,avgc_a,avgc_o25,avgc_u25 from fd_match where match_id is not null and fthg is not null and avgc_h is not null and avgc_o25 is not null").fetchall()
L=[];G=np.arange(11);tot=G[:,None]+G[None,:]
for mid,se,h,a,oh,od,oa,oo,ou in rows:
    j=pos.get(mid)
    if j is None or not np.isfinite(d['lh'][j]):continue
    M=score_matrix(np.array([d['lh'][j]]),np.array([d['la'][j]]),float(d['rho'][j]))[0];n=M.shape[0];t=tot[:n,:n]
    pH=np.tril(M,-1).sum();pD=np.trace(M);pA=np.triu(M,1).sum();pO=(M*(t>2.5)).sum()
    sh=shin([oh,od,oa]) or [1/oh,1/od,1/oa];s2=1/oo+1/ou
    for pm,o,mk,y in ((pH,oh,sh[0],h>a),(pD,od,sh[1],h==a),(pA,oa,sh[2],h<a),(pO,oo,(1/oo)/s2,h+a>2.5),(1-pO,ou,(1/ou)/s2,h+a<2.5)):
        L.append((se,float(pm),o,float(mk),bool(y)))
pickle.dump(L,open('legs.pkl','wb'))
lg=lambda p:math.log(max(1e-6,p)/max(1e-6,1-p));sg=lambda z:1/(1+math.exp(-z))
for per,f in (('P1 21-24',lambda s:s<'2425'),('P2 24-27',lambda s:s>='2425')):
  ls=[l for l in L if f(l[0])]
  for w in (0.0,0.05,0.1,0.15,0.2,0.3):
    for th in (0.0,0.02,0.04):
      s=[(sg(w*lg(l[1])+(1-w)*lg(l[3])),l) for l in ls if 1.3<=l[2]<=4]
      s=[(p,l) for p,l in s if p*l[2]-1>th]
      if len(s)<20: continue
      e=sum(p for p,_ in s);r=sum(l[4] for _,l in s);roi=sum(l[2]*l[4] for _,l in s)/len(s)-1
      sd=math.sqrt(sum((l[2]*l[4]-1-roi)**2 for _,l in s))/len(s)
      print(per,'w=%.2f th=%.2f n=%5d real/exp=%.3f predEV=%+.3f ROI=%+.3f±%.3f'%(w,th,len(s),r/e,sum(p*l[2]-1 for p,l in s)/len(s),roi,sd))
