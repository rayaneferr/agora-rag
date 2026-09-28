# Attributions et licences

Le code de ce dépôt est sous licence MIT (voir [LICENSE](LICENSE)). Les données qu'il indexe ne le sont pas :
elles restent sous la licence de leur producteur, rappelée ci-dessous. L'index publié sur Hugging Face
([rferrat/agora-rag-index](https://huggingface.co/datasets/rferrat/agora-rag-index)) suit ces licences, table par
table. Le dépôt lui-même ne contient pas ces données, en dehors d'une séance fictive utilisée par les tests.

## Comptes rendus des débats de l'Assemblée nationale (table `debats`)

- **Producteur** : Assemblée nationale.
- **Source** : comptes rendus des séances publiques, 17e législature, format XML Syceron,
  https://data.assemblee-nationale.fr/travaux-parlementaires/debats
- **Date des données** : séances du 18 juillet 2024 au 21 juillet 2026, téléchargées pour l'index publié le
  28 septembre 2026.
- **Licence** : Licence Ouverte / Open Licence (Etalab, version d'octobre 2011),
  https://data.assemblee-nationale.fr/licence-ouverte-open-licence
- **Modifications** : interventions reconstituées à partir des paragraphes, interjections écartées, noms
  d'orateurs normalisés, découpage en extraits et calcul d'embeddings. Le texte des interventions n'est pas réécrit.

## Synopsis de films (table `films`)

- **Auteurs** : les contributeurs de Wikipédia en anglais (sections « Plot » des articles de films),
  https://en.wikipedia.org/
- **Collecte** : *Wikipedia Movie Plots*, JustinR, Kaggle, 2018,
  https://www.kaggle.com/datasets/jrobischon/wikipedia-movie-plots
- **Résumés courts** : *Wikipedia Movie Plots with AI Plot Summaries*, Gabriel Tardochi, Kaggle, 2021, générés
  avec le modèle DistilBART-CNN-12-6,
  https://www.kaggle.com/datasets/gabrieltardochi/wikipedia-movie-plots-with-plot-summaries
- **Copie utilisée** : https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries
- **Licence** : Creative Commons Attribution – Partage dans les mêmes conditions 4.0 (CC BY-SA 4.0),
  https://creativecommons.org/licenses/by-sa/4.0/
- **Modifications** : métadonnées inconnues vidées, découpage en extraits et calcul d'embeddings. La table
  `films` est une adaptation distribuée sous la même licence.

## Modèle d'embeddings

- **BAAI/bge-m3**, licence MIT, https://huggingface.co/BAAI/bge-m3 — téléchargé à une révision épinglée, non
  redistribué par ce dépôt.
