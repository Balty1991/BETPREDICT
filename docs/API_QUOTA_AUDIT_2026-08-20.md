# Audit utilizare API BSD — 2026-08-20

## Sursa externă

Documentația oficială BSD: [Conventions & limits](https://sports.bzzoiro.com/docs/conventions/), consultată la 2026-08-20.

API-ul Football v2 folosește baza `https://sports.bzzoiro.com/api/v2/`. Planul gratuit permite **7.500 de cereri/zi**, resetate la miezul nopții UTC. La epuizare, API-ul răspunde cu HTTP `429` și codul `taster_exhausted`, alături de `Retry-After`. Documentația indică utilizarea câmpurilor `RateLimit` pentru telemetrie, recomandă cache și recomandă ca endpointurile live să nu fie interogate mai des de 10 secunde; cotele sunt reîmprospătate mai rar și suportă filtrare `updated_after` la endpointul general de cote.

Endpointul `/api/v2/odds/best/` oferă, pentru fiecare eveniment viitor și piață cerută, cea mai bună cotă decimală pentru fiecare rezultat, cu cache de aproximativ 5 minute. Endpointurile `/api/v2/predictions/` oferă predicții calibrate și ancorate în piață unde există consens. Endpointul `/api/v2/events/live/` este construit pentru interogare frecventă și are cache de 30 secunde.

## Constatare locală

Raportul de acoperire din `data/api_coverage_final.json` a arătat 29 din 29 apeluri de sondare în eroare `429`, iar colectorul de date aprofundate a raportat 416 erori `429` pentru 104 evenimente × 4 subresurse. Acest fapt explică de ce cota se epuizează înainte de actualizarea cotelor și de ce fișierele de cote rămân expirate.

## Decizie de implementare

Pipeline-ul orar va prioritiza predicțiile și cotele consolidate pe piețele 1X2, Over/Under 1.5/2.5/3.5, BTTS și Double Chance. Îmbogățirea profundă se va roti o dată pe zi, iar forma echipelor la șase ore. Scanerul de sondare de endpointuri trebuie eliminat din ciclul orar și înlocuit cu telemetrie bazată pe apelurile reale deja efectuate.
