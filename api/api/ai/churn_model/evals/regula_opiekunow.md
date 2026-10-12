# regula_opiekunow: punkt odniesienia

Reguła opiekunów: **biuro jest zagrożone, jeśli umowa kończy się w ciągu 90 dni, a zaparzenia z 30 dni są o ponad
30% niższe od średniej z 90 dni** (`iot_telemetria`).

**AUC = 0,7028** na tym samym zbiorze testowym co v0_agencja (2 470 wierszy, 87 odejść). Reguła oznacza 84 wiersze
i trafia 37 odejść: **precyzja 44,0%, czułość 42,5%**. Reguła daje tylko 0 albo 1, więc jej AUC to średnia czułości
i swoistości (0,4253 + 0,9803) / 2.

## 1. Jak liczone

| | |
|---|---|
| Zbiór testowy | ten sam co v0_agencja: `zbior_agencji.py`, losowy podział 80/20, seed 42. Reguła się nie uczy, więc część ucząca jest nieużywana |
| „Umowa kończy się w ciągu 90 dni” | `dni_do_konca_okresu < 90`: dni od snapszotu do końca bieżącego rocznego okresu umowy (najbliższa rocznica `data_startu` minus 1 dzień). Nie bierzemy `crm_biura.data_konca_umowy` ani `dni_do_konca_umowy` agencji, bo to stan z dnia eksportu |
| „Zaparzenia z 30 dni” | suma zaparzeń wszystkich ekspresów biura z 30 ostatnich znanych dni |
| „Średnia z 90 dni” | suma z 90 ostatnich znanych dni / 3, czyli średnia 30-dniowa. Okno 90 dni obejmuje okno 30 dni |
| „O ponad 30% niższe” | `zaparzenia_30d < 0,7 × zaparzenia_90d / 3`; spadek dokładnie o 30% nie wystarcza |
| Ostatni znany dzień | telemetria dociera zawsze 2 dni po pomiarze (`data_dostarczenia = data + 2`), więc w dniu snapszotu `d` ostatni znany dzień to `d − 3`. Okna: `[d − 32, d − 3]` i `[d − 92, d − 3]` |
| Brak telemetrii | 3 wiersze testowe nie mają telemetrii, więc ich sumy to 0 i warunek spadku jest fałszywy |
| Kod | `versions/regula_opiekunow/` (`cechy.sql`, `model.py`, `ocen.py`); wynik w `versions/regula_opiekunow/artefakty/ocena.json` |

```bash
PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.regula_opiekunow.ocen
```

Cech nie bierzemy z tabeli agencji. Jej `zaparzenia_30d` zgadza się z naszą sumą 30-dniową tylko w 3% wierszy, a
`dni_do_konca_umowy` przecieka (evals/v0_agencja.md).

## 2. Wpływ pojedynczych interpretacji

Każdy wiersz to **jedna** zmiana względem definicji z sekcji 1, liczona na tym samym zbiorze testowym.

| Wariant | AUC | Oznaczone | Trafione | Precyzja | Czułość |
|---|---:|---:|---:|---:|---:|
| **reguła (sekcja 1)** | **0,7028** | **84** | **37** | **44,0%** | **42,5%** |
| „w ciągu 90 dni” jako `<= 90` | 0,7028 | 84 | 37 | 44,0% | 42,5% |
| średnia z 60 dni sprzed okna 30 dni zamiast z całych 90 | 0,7126 | 94 | 39 | 41,5% | 44,8% |
| okna do `d − 1`, bez opóźnienia dostawy (nieznane w dniu snapszotu) | 0,6923 | 77 | 35 | 45,5% | 40,2% |
| `dni_do_konca_umowy` agencji zamiast okresu z rocznicy (przeciek) | 0,7126 | 37 | 37 | 100,0% | 42,5% |
| tylko warunek umowy | 0,7350 | 555 | 59 | 10,6% | 67,8% |
| tylko warunek spadku zaparzeń | 0,7073 | 318 | 46 | 14,5% | 52,9% |

Wnioski:
- Wynik jest stabilny przy rozsądnych interpretacjach (0,69–0,71).
- Z przeciekającą datą końca umowy reguła ma 100% precyzji. Każde oznaczone biuro odchodzi, bo „kończy się w 90 dni”
  znaczy wtedy „już wiadomo, że nie odnowi”.
- Warunek umowy łapie najwyżej 59 z 87 odejść (67,8%). Wypowiedzenie może przyjść w dowolnym momencie roku, a nie
  tylko przed rocznicą, więc reguła z tym warunkiem z założenia nie widzi części odejść.
- Sam warunek umowy ma wyższe AUC niż cała reguła (0,735 vs 0,703), ale oznacza 6,6× więcej biur. AUC reguły 0/1
  nagradza czułość, więc lepiej porównywać ją z modelami także przy tej samej liczbie oznaczonych biur (precyzja przy 84).
