import pickle,sqlite3,math,numpy as np,random,sys,json
sys.path.insert(0,'/workspace/bp-analysis')
from betpredict.model.dc import score_matrix
d=pickle.load(open('wf45.pkl','rb'));pos={int(i):j for j,i in enumerate(d['ids'])}
c=sqlite3.connect('file:fd.db?mode=ro',uri=True)
rows=c.execute("select match_id,season,day,fthg,ftag,avgc_h,avgc_d,avgc_a,avgc_o25,avgc_u25 from fd_match where match_id is not null and fthg is not null and avgc_h is not null and avgc_o25 is not null").fetchall()
L=[]
G=np.arange(11);tot=G[:,None]+G[None,:]
for mid,se,day,h,a,oh,od,oa,oo,ou in rows:
    j=pos.get(mid)
    if j is None or not np.isfinite(d['lh'][j]):continue
    M=score_matrix(np.array([d['lh'][j]]),np.array([d['la'][j]]),float(d['rho'][j]))[0]
    n=M.shape[0];t=tot[:n,:n]
    pH=np.tril(M,-1).sum();pD=np.trace(M);pA=np.triu(M,1).sum();pO=(M*(t>2.5)).sum()
    s=1/oh+1/od+1/oa;s2=1/oo+1/ou
    for pm,o,mk,y in ((pH,oh,(1/oh)/s,h>a),(pD,od,(1/od)/s,h==a),(pA,oa,(1/oa)/s,h<a),(pO,oo,(1/oo)/s2,h+a>2.5),(1-pO,ou,(1/ou)/s2,h+a<2.5)):
        L.append((se,day,float(pm),o,mk,bool(y)))
lg=lambda p:math.log(max(1e-6,p)/max(1e-6,1-p));sg=lambda z:1/(1+math.exp(-z))
def blend(l,w):return sg(w*lg(l[2])+(1-w)*lg(l[4]))
def prud(l):return 0.7*l[2]+0.3*l[4]  # producție actuală (p_prudent, cu p model)
tr=[l for l in L if l[0]<'2425'];te=[l for l in L if l[0]>='2425']
print(len(tr),len(te))
def sel(ls,f):return [l for l in ls if 1.3<=l[3]<=4 and f(l)*l[3]>1]
for nm,f in [('prod 0.7/0.3',prud)]+[('w=%.2f'%w,(lambda w:lambda l:blend(l,w))(w)) for w in (0.0,0.1,0.2,0.3,0.5)]:
    for per,ls in (('train',tr),('test',te)):
        s=sel(ls,f)
        if not s: print(nm,per,0);continue
        p=sum(f(l) for l in s)/len(s);y=sum(l[5] for l in s)/len(s);roi=sum(l[3]*l[5] for l in s)/len(s)-1
        print(nm,per,len(s),'p %.3f hit %.3f predEV %+.3f ROI %+.3f'%(p,y,sum(f(l)*l[3]-1 for l in s)/len(s),roi))
# fit global shrink factor k on train: hit ≈ k*p for selected legs (selection-aware), using prod selection
s=sel(tr,prud);k=sum(l[5] for l in s)/sum(prud(l) for l in s);print('k_train',round(k,4))
st=sel(te,prud);print('k_test',round(sum(l[5] for l in st)/sum(prud(l) for l in st),4))
json.dump(dict(k=k),open('accbt.json','w'))
# N-leg tickets on test: random legs from selected pool in same week
random.seed(3)
from collections import defaultdict
wk=defaultdict(list)
for l in st: wk[l[1][:8]].append(l)
wks=[v for v in wk.values() if len(v)>=12]
for n in (3,5,7,10):
    P=Pk=Y=R=0;N=20000
    for _ in range(N):
        v=random.choice(wks);ls=random.sample(v,n)
        p=math.prod(prud(l) for l in ls);P+=p;Pk+=math.prod(min(.99,k*prud(l)) for l in ls)
        y=all(l[5] for l in ls);Y+=y;R+=math.prod(l[3] for l in ls)*y
    print('legs',n,'pred hit %.4f  shrunk %.4f  real %.4f  realROI %+.2f'%(P/N,Pk/N,Y/N,R/N-1))
