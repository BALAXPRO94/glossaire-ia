# Glossaire IA + Veille

Un seul site : le **glossaire** des créateurs IA (liens YouTube / GitHub) et un **tableau de bord de veille** mis à jour automatiquement.

## Fichiers

| Fichier | Rôle |
|---|---|
| `people.json` | Source unique des personnes (liens publics vérifiés). |
| `sources.json` | Flux de news, releases suivies, réglages de découverte. |
| `collect.py` | Collecte YouTube / GitHub / news, écrit `data/feed.json` et `data/candidates.json`. |
| `template.html` + `build.py` | Génèrent `index.html` (glossaire + veille). |
| `.github/workflows/veille.yml` | Collecte toutes les 3 h, commit des données, déploiement GitHub Pages. |
| `tests/test_collect.py` | Test hors ligne du collecteur (moins de 2 s). |
| `data/ignored.json` | (optionnel) liste de logins GitHub à ne plus proposer comme candidats. |

## Mise en route (une seule fois)

1. Créer un dépôt **public** et y pousser ces fichiers (branche `main`).
2. Réglages du dépôt, Pages : source **GitHub Actions**.
3. Onglet Actions, workflow **Veille** : « Run workflow ». Le site apparaît à l'adresse affichée par l'étape de déploiement.

Aucun secret à créer : le collecteur utilise le jeton fourni automatiquement par GitHub.

## Ajouter une personne, une source

- Personne : une entrée dans `people.json` (le collecteur retrouve seul l'identifiant de la chaîne YouTube).
- Source de news : une ligne dans `sources.json`, section `news`. Mettre `"verified": null` tant que le flux n'a pas été ouvert à la main ; l'état de chaque source est affiché dans le tableau de bord.
- Candidat proposé par la découverte : le bouton « Copier l'entrée » du tableau de bord donne l'entrée prête à coller dans `people.json`.

## Limites connues

- GitHub désactive les workflows planifiés d'un dépôt public après 60 jours sans activité. Le tableau de bord signale un relevé de plus de 24 h.
- La découverte de nouveaux créateurs ne couvre que GitHub (sujets `claude-skills`, `agent-skills`, `claude-code`). Sur YouTube elle demanderait une clé d'API.
- Le collecteur ne garde que titre, lien, date, auteur et un court extrait. Aucune vidéo ni contenu complet n'est stocké.
