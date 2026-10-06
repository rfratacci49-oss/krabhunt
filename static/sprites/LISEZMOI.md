# Sprites locaux

Déposez ici vos propres sprites shiny, **un dossier par jeu**. Ils remplacent
automatiquement ceux de PokeAPI ; tout sprite absent est chargé depuis PokeAPI.
Aucun redémarrage nécessaire : un fichier ajouté s'affiche au prochain chargement de page.

## Nommer les fichiers

Le nom du fichier est le **numéro du Pokédex national**, sans zéros devant :

| Fichier             | Pokémon                                  |
|---------------------|------------------------------------------|
| `hgss/94.png`       | Ectoplasma dans HeartGold / SoulSilver |
| `hgss/25.png`       | Pikachu (mâle ou sans distinction) |
| `hgss/25-f.png`     | Pikachu femelle (facultatif)       |
| `nb/635.gif`        | Trioxhydre animé dans Noir / Blanc   |
| `ev/1000.webp`      | Gromago dans Écarlate / Violet    |

- Formats acceptés : `png`, `gif`, `webp`, `jpg`.
- `-f` = version femelle. Si elle n'existe pas, le sprite standard est utilisé.
- Le numéro d'un Pokémon est affiché sur sa carte dans la collection (`#0094`).

## Formes (régionales ou autres)

Ajoutez la **clé de la forme** après le numéro :

| Fichier                  | Pokémon                         |
|--------------------------|---------------------------------|
| `sl/19-alola.png`        | Rattata d’Alola                 |
| `epee_bouclier/52-galar.png` | Miaouss de Galar            |
| `hgss/201-b.png`         | Zarbi B                         |
| `xy/666-polar.png`       | Prismillon Motif Banquise       |
| `xy/666-polar-f.png`     | idem, version femelle           |

Les clés de toutes les formes sont dans `data/forms_fr.json`
(ex. `"19": {"forms": {"alola": …}}` → clé `alola`).

## Ordre de recherche

1. `static/sprites/<jeu>/<numéro>[-<forme>]-f.<ext>` (si le Pokémon est femelle)
2. `static/sprites/<jeu>/<numéro>[-<forme>].<ext>`
3. Sprite PokeAPI du jeu (jusqu'à la 6e génération)
4. Sprite PokeAPI de Pokémon HOME

## Dossiers

| Famille | Jeu | Dossier |
|---------|-----|---------|
| Or / Argent / Cristal | Or | `or/` |
| Or / Argent / Cristal | Argent | `argent/` |
| Or / Argent / Cristal | Cristal | `cristal/` |
| Rubis / Saphir / Émeraude | Rubis / Saphir | `rs/` |
| Rubis / Saphir / Émeraude | Émeraude | `emeraude/` |
| Rouge Feu / Vert Feuille | Rouge Feu / Vert Feuille | `rfvf/` |
| Pokémon Colosseum | Pokémon Colosseum | `colosseum/` |
| Pokémon XD : Le Souffle des Ténèbres | Pokémon XD : Le Souffle des Ténèbres | `xd/` |
| Diamant / Perle / Platine | Diamant / Perle | `dp/` |
| Diamant / Perle / Platine | Platine | `platine/` |
| Pokémon Battle Revolution | Pokémon Battle Revolution | `pbr/` |
| HeartGold / SoulSilver | HeartGold / SoulSilver | `hgss/` |
| Pokémon Rumble | Pokémon Rumble | `rumble/` |
| Noir / Blanc / Noir 2 / Blanc 2 | Noir / Blanc | `nb/` |
| Noir / Blanc / Noir 2 / Blanc 2 | Noir 2 / Blanc 2 | `nb2/` |
| X / Y | X / Y | `xy/` |
| Rubis Oméga / Saphir Alpha | Rubis Oméga / Saphir Alpha | `rosa/` |
| Soleil / Lune / Ultra-Soleil / Ultra-Lune | Soleil / Lune | `sl/` |
| Soleil / Lune / Ultra-Soleil / Ultra-Lune | Ultra-Soleil / Ultra-Lune | `usul/` |
| Let's Go Pikachu / Évoli | Let's Go Pikachu / Évoli | `lgpe/` |
| Épée / Bouclier | Épée / Bouclier | `epee_bouclier/` |
| Diamant Étincelant / Perle Scintillante | Diamant Étincelant / Perle Scintillante | `deps/` |
| Légendes Pokémon : Arceus | Légendes Pokémon : Arceus | `lpa/` |
| Écarlate / Violet | Écarlate / Violet | `ev/` |
| Légendes Pokémon : Z-A | Légendes Pokémon : Z-A | `lza/` |
| Pokémon HOME | Pokémon HOME | `home/` |
