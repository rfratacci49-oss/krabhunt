# Pokédex du Shinydex

Un fichier par Pokédex, modifiable avec n'importe quel éditeur de texte
(Bloc-notes, VS Code…). Les changements s'affichent au prochain chargement de la page
Shinydex, **sans redémarrer le site**.

| Fichier | Pokédex |
|---------|---------|
| `national.json` | Pokédex national |
| `<famille>.json` | Pokédex de la famille de jeux (le nom du fichier est la clé de `FAMILIES` dans `pokemon.py` : `oac.json` = Or / Argent / Cristal, `ev.json` = Écarlate / Violet…) |

## Format

Exemple raccourci (les vraies listes sont complètes) :

```json
{
  "nom": "Écarlate / Violet",
  "sections": [
    {
      "titre": "Paldea",
      "pokemon": [
        "Poussacha",
        "Matourgeon",
        "Miascarade"
      ]
    },
    {
      "titre": "Septentria",
      "pokemon": [
        "Mascaïman",
        "Pikachu"
      ]
    }
  ]
}
```

- **`pokemon`** : la liste des Pokémon, **dans l'ordre du Pokédex, un par ligne**.
  Le numéro régional est la position dans la liste : le 1er est le n° 1, le 2e le n° 2…
  - Ajouter un Pokémon : insérer une ligne `"Nom",` à sa place.
  - Retirer un Pokémon : supprimer sa ligne (les numéros suivants se décalent).
  - Nom en français, tel qu'affiché sur le site. Accents et majuscules libres
    (`"evoli"` = `"Évoli"`). On peut aussi écrire le n° national : `25` ou `"#25"`.
  - **Formes** : écrire le nom complet de la forme, comme sur le site :
    `"Rattata d’Alola"` (ou `"Rattata d'Alola"`), `"Miaouss de Galar"`, `"Zarbi B"`,
    `"Prismillon Banquise"`… La case affiche alors le sprite de cette forme et n'est cochée
    que par un shiny de cette forme. Un nom sans forme (`"Rattata"`) est coché par
    n'importe quelle forme de l'espèce.
  - Une même espèce peut apparaître plusieurs fois avec des formes différentes
    (ex. `"Miaouss"` et `"Miaouss de Galar"`), mais pas deux fois avec la même.
  - Les noms de toutes les formes sont dans `data/forms_fr.json` (champ `"full"`).
- **`debut`** (facultatif) : numéro du premier Pokémon de la section, 1 par défaut.
  Exemple : `"debut": 0` pour Unys, qui commence par Victini au n° 000.
- **`sections`** : un Pokédex peut en avoir plusieurs (Kalos Centre / Côtes / Monts,
  Galar / Isolarmure / Couronneige…). Chacune a sa numérotation et sa progression.
- **`titre`** : nom affiché au-dessus de la section.
- **`nom`** : nom du Pokédex (informatif ; le libellé affiché vient de `pokemon.py`).

## Pièges JSON

- Chaque ligne de la liste se termine par une virgule, **sauf la dernière**.
- Les noms sont entre guillemets droits `"…"`.
- Si le fichier est mal formé ou qu'un nom est inconnu, le site continue de fonctionner :
  le problème est affiché en haut de la page Shinydex, avec le fichier, la section, le
  numéro concerné et une suggestion de nom (« vouliez-vous dire « Pikachu » ? »).

## Origine

Les fichiers ont été générés depuis les Pokédex de [PokeAPI](https://pokeapi.co).
Les formes régionales natives y ont été placées : formes d'Alola dans `slusul.json`,
de Galar dans `epee_bouclier.json` (Galar, Isolarmure, Couronneige), de Hisui dans
`lpa.json` et de Paldea dans la section Paldea d'`ev.json` (Tauros est laissé sans forme :
ses trois races de Paldea sont toutes possibles).
Colosseum, XD, Battle Revolution, Rumble et HOME n'ayant pas de Pokédex régional,
leur fichier contient le Pokédex national limité aux générations du jeu.
