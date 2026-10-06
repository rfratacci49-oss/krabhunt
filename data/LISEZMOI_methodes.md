# Méthodes de chasse (`methodes.json`)

Liste des méthodes proposées dans les formulaires (ajout de shiny, nouvelle chasse), avec
les jeux où elles existent et leur taux shiny. Modifiable avec n'importe quel éditeur de
texte ; les changements sont pris en compte au prochain chargement de page, **sans
redémarrer le site**. Une erreur dans le fichier est signalée sous le champ « Méthode ».

Le taux s'affiche :
- sous le champ « Méthode » des formulaires (selon le jeu et la case « Charme chroma ») ;
- sur la page du compteur, avec la probabilité d'avoir déjà trouvé le shiny ;
- sur chaque carte de la collection (« 1/4 096 » à côté de la méthode).

La méthode reste un texte libre : une méthode absente du fichier est acceptée, simplement
sans taux.

## Ajouter une méthode

Copiez un bloc dans la liste `"methodes"` (attention aux virgules entre les blocs) :

```json
{
  "nom": "Ma méthode",
  "alias": ["Autre nom", "Ancien nom"],
  "description": "Texte affiché dans les suggestions (facultatif)",
  "jeux": [
    {"jeux": ["xy", "rosa"], "taux": 512, "charme": 256, "note": "Chaîne de 40"},
    {"jeux": ["ev"], "taux": 1024}
  ]
}
```

| Champ | Rôle |
|-------|------|
| `nom` | Nom affiché et enregistré sur le shiny. |
| `alias` | Facultatif : autres libellés reconnus comme cette méthode (anciens noms, fautes de frappe). Majuscules, accents et ponctuation sont déjà ignorés (« peche a la chaine » = « Pêche à la chaîne »). |
| `description` | Facultatif : précision affichée dans la liste de suggestions. |
| `jeux` | Une liste de lignes (ci-dessous), ou `"standard"` (taux de base du jeu, voir plus bas), ou `"tous"` (tous les jeux ; mettre alors `taux` / `charme` / `note` directement dans le bloc de la méthode). |
| `sauf` | Facultatif, avec `"standard"` ou `"tous"` : jeux à retirer (ex. `["lgpe", "lpa"]` pour les œufs). |
| `remplace` | Facultatif, avec `"standard"` ou `"tous"` : lignes (même format que `jeux`) qui remplacent le taux de certains jeux (ex. Resets dans PixelmonWorld). |

Chaque ligne de `jeux` :

| Champ | Rôle |
|-------|------|
| `jeux` | Clés des jeux concernés (voir la liste ci-dessous). |
| `taux` | Taux sans charme chroma, « 1 sur N » : `4096` pour 1/4096, `1` pour un shiny garanti, `null` si variable ou inconnu. |
| `charme` | Facultatif : taux avec le charme chroma. Absent = le charme ne change rien. |
| `note` | Facultatif : condition du taux (« Chaîne de 40 »…). |

## Taux de base (`"standard"`)

Le bloc `"standard"` en haut du fichier donne le taux de base de chaque jeu (rencontre
classique). Les méthodes `"jeux": "standard"` (Rencontres, Resets, Shiny hasard…)
le reprennent : corriger un taux ici le corrige pour toutes ces méthodes.

## Clés des jeux

`or`, `argent`, `cristal`, `rs` (Rubis / Saphir), `emeraude`, `rfvf`, `colosseum`, `xd`,
`dp` (Diamant / Perle), `platine`, `pbr`, `hgss`, `rumble`, `nb` (Noir / Blanc), `nb2`,
`xy`, `rosa` (Rubis Oméga / Saphir Alpha), `sl` (Soleil / Lune), `usul`, `lgpe`,
`epee_bouclier`, `deps` (Diamant Étincelant / Perle Scintillante), `lpa` (Légendes Arceus),
`ev` (Écarlate / Violet), `lza` (Légendes Z-A), `home`.
