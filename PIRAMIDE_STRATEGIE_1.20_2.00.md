# Strategia implementată: Piramida Streak 1.20 și Value 2.00

## Scop

Aplicația urmărește două piste independente. Prima maximizează frecvența și lungimea seriilor, iar a doua caută o creștere mai rapidă cu un număr limitat de selecții. Niciuna nu garantează profit; o zi fără candidat este preferată unui bilet forțat.

## 1. Piramida Streak 1.20

- Cotă țintă pe treaptă: **1,16–1,25**.
- Maximum: **31 de pași**.
- Filtru: selecție confirmată de piață, probabilitate prudentă și protecție la două pierderi consecutive.
- Se încearcă un singur meci pe zi; nu se construiește o acumulare lungă doar pentru a atinge cota.
- Banca de start este configurabilă local în interfață.
- Graficul afișează orientativ banca și șansa de a ajunge la fiecare treaptă.

## 2. Piramida Value 2.00

- Cotă totală pe treaptă: **1,85–2,20**.
- Maximum: **10 pași**.
- Maximum două selecții pe bilet, numai favoriți 1X2 și numai din ligi non-top.
- EV minim de siguranță: **−3%**, cu probabilitate prudentă și selecții de cel mult 1,40 individual.
- După două pierderi consecutive se activează pauza de protecție.
- Se recomandă miză controlată și retragerea orientativă a 50% din profit, nu creșterea mizei după pierderi.

## Retrageri și restart

În ambele piste, utilizatorul poate seta orice miză de start. La fiecare treaptă este afișată suma orientativă dacă biletul intră. Retragerea parțială scade suma aflată în joc, iar restul continuă să urmărească seria. Dacă se retrage tot, seria personală poate fi închisă și reluată de la treapta 1; seria oficială a robotului rămâne separată.

Monitorizarea păstrează aceleași informații pentru ambele piste: ziua, biletul, rezultatul, treapta, run-ul, banca, suma retrasă, recordul și statistica de reach pe trepte. Bănuții retrași sunt separați de banca reinvestită.

## Regula financiară recomandată

Folosește o miză inițială mică și fixă. Nu recupera pierderile prin martingale și nu considera proiecția de la treapta 20 sau 31 drept rezultat probabil. Retrage periodic profitul; scopul este să reduci capitalul expus, nu să maximizezi cifra teoretică.

## Verificare tehnică

Implementarea a fost verificată prin 24 de teste backend, compilare Python fără erori și verificare TypeScript fără erori. Build-ul Vite complet depinde de autorizarea scriptului esbuild în mediul local; problema este de instalare, nu de cod TypeScript.
