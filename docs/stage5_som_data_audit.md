# Stage 5 SOM data audit — opening note

The current frozen Census 2022 sector artifact already supports female rurality and partial female age composition. It does **not** currently materialize municipal income, literacy/education, or race/color features. Those blocks must be acquired from official Census 2022 municipal dissemination and audited separately before SOM training.

The SOM data build must preserve the 144 Pará municipalities, explicit source/year metadata, and suppression/missingness without synthetic filling.

Priority for acquisition:
1. race/color composition (Census 2022 universe; SIDRA official dissemination, including table 9605);
2. literacy/education (Census 2022 municipal literacy universe results; exact table identifiers to be locked from official metadata);
3. income/poverty (Census 2022 municipal indicator with explicit definition and complete/known coverage).

No SOM training is authorized until this data audit is closed.
