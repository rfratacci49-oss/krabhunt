# KRABHUNT ✨

Vitrine de collections de Pokémon shiny — Flask + SQLite.

- Chacun peut créer un compte (`/register`) et gérer **sa propre** collection.
- L'accueil liste les chasseurs avec un aperçu de leurs derniers shiny.
- Chaque collection est publique sur `/u/<pseudo>` ; seul son
  propriétaire peut ajouter, modifier ou supprimer.
- **Compteur** (`/compteur`) : compteur de rencontres pour les chasses en cours (voir plus bas).

## Collections séparées

Les shiny des jeux non officiels **PixelmonWorld** et **Cobblemon** forment des collections
indépendantes de la collection principale (jeux officiels) : `/u/<pseudo>/pixelmonworld` et
`/u/<pseudo>/cobblemon`, chacune avec ses filtres, ses statistiques, son Shinydex (Pokédex
national seul, sprites HOME) et ses exports. Des onglets passent d'une collection à l'autre ;
l'accueil compte la collection principale et indique à part le nombre de shiny des autres.
Le jeu choisi dans la fiche du shiny décide de sa collection.
Pour ajouter une collection : un jeu dans `GAMES`, sa famille dans `FAMILIES` et une entrée dans
`COLLECTIONS` (`pokemon.py`), puis son taux de base dans le bloc `"standard"` de `data/methodes.json`.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Lancement

```powershell
python app.py
```

Puis ouvrir http://127.0.0.1:5000. La base `krabhunt.db` est créée automatiquement.

## Données d'un shiny

| Champ           | Détail                                                         |
|-----------------|----------------------------------------------------------------|
| Pokémon         | Nom français avec autocomplétion (Pokédex national, 1025 esp.) ; accepte aussi le n° (« 25 ») ou le nom sans accents (« evoli ») |
| Forme           | Formes régionales ou alternatives (386 formes, 125 espèces) : la liste apparaît quand l'espèce en a |
| Surnom          | Facultatif                                                     |
| Jeu de capture  | Liste dans `pokemon.py` (`GAMES`), regroupés en familles (`FAMILIES`) pour l'affichage et le filtre |
| Méthode         | Texte libre ; suggestions et taux shiny selon le jeu, depuis `data/methodes.json` (modifiable, voir `data/LISEZMOI_methodes.md`) |
| Genre           | ♂ / ♀ / asexué                                                 |
| Date            | Facultative                                                    |
| Poké Ball       | Facultative, liste dans `pokemon.py` (`BALLS`) avec icône      |
| Rencontres      | Facultatif, entier ≥ 0                                         |
| Temps de chasse | Facultatif, H:MM:SS (rempli par le timer du compteur)          |
| Lieu            | Texte libre facultatif (100 caractères max.)                   |
| Charme chroma   | Case à cocher (possédé ou non lors de la capture)              |
| Note            | Texte libre facultatif (1000 caractères max.)                  |
| Phases          | Shiny de la collection trouvés avant la cible (choisis dans la fiche de la cible, dans l'ordre). Affichage : « Phase N » sur chaque phase, « Phase finale » sur la cible |
| Sprite          | Automatique selon jeu + genre, ou URL personnalisée            |

### Sprites

Les sprites viennent du dépôt [PokeAPI/sprites](https://github.com/PokeAPI/sprites) :

- Gen 2 à 6 (Or → ROSA) : sprite shiny du jeu (animé pour Noir/Blanc).
- Colosseum, XD : sprites d'Émeraude ; Battle Revolution : sprites de Platine ; Rumble : sprites HOME.
- Gen 7+ (Soleil/Lune → Z-A), HOME : sprite shiny de Pokémon HOME.
- Femelle : sprite femelle si l'espèce a un dimorphisme, sinon sprite standard.

Vos propres sprites peuvent être déposés dans `static/sprites/<jeu>/` (ex. `hgss/94.png`,
`hgss/25-f.png` pour une femelle) : ils passent avant PokeAPI. Voir `static/sprites/LISEZMOI.md`.

Les formes ont leur propre sprite (ex. Rattata d’Alola, Zarbi B), local ou PokeAPI.

## Filtres de la collection

Recherche libre (nom, surnom, forme, méthode, lieu, note, n° de Pokédex exact, sans tenir compte
des accents, avec suggestions des espèces de la collection), jeu, génération, méthode, Poké Ball, charme chroma, genre, phases (phase finale / phase / sans),
forme (base / alternative), année, nombre de rencontres (min–max).
Tris : date, derniers ajoutés, rencontres, temps de chasse, n° de Pokédex, nom. Rangement (« Ranger ») par
famille de jeux, par date de capture (une section par année, ordre chronologique, jeu ignoré)
ou en liste unique ; le dernier rangement choisi est retenu pour les visites suivantes. Les filtres sont dans l'URL : une vue filtrée peut être partagée.
Le code est dans `filters.py`.

## Shinydex

Lien « ✨ Shinydex » en haut de la collection (`/u/<pseudo>/shinydex`) : grille du Pokédex
avec les sprites shiny de Pokémon HOME, en couleur si l'espèce est capturée (toutes formes
confondues, ×N si plusieurs), grisée sinon. Chaque case capturée mène aux shiny concernés.

- **Pokédex national** (1025) : toutes les captures comptent.
- Sprites : HOME dans le Pokédex national. Dans un Pokédex de famille, le sprite de votre
  shiny (son jeu, sa forme, son genre) ou, s'il manque, celui du jeu le plus récent de la
  famille (Cristal, Émeraude, Platine…) ; HOME pour les familles sans sprites propres.
- **Un Pokédex par famille de jeux** (Johto pour Or/Argent/Cristal, Galar + Isolarmure +
  Couronneige pour Épée/Bouclier…) avec les numéros régionaux : seules les captures faites
  dans les jeux de la famille comptent.
- Affichage tous / capturés / manquants, recherche par nom (accents facultatifs) ou par n°
  (national ou régional), progression par Pokédex.
- Les formes régionales natives sont dans les Pokédex (Rattata d’Alola dans Alola, Miaouss de
  Galar dans Galar…) : une case de forme n'est cochée que par un shiny de cette forme.

Les Pokédex sont des fichiers **modifiables à la main** dans `data/shinydex/`
(`national.json` + un `<famille>.json` par famille) : une liste de noms de Pokémon dans
l'ordre du Pokédex, le numéro régional étant la position dans la liste. Les changements
s'affichent sans redémarrer ; une erreur (nom inconnu, JSON mal formé) est signalée en haut
de la page Shinydex sans bloquer le site. Format détaillé : `data/shinydex/LISEZMOI.md`.
Colosseum, XD, Battle Revolution, Rumble et HOME, sans Pokédex régional, contiennent le
national limité à leurs générations. Une famille ajoutée dans `pokemon.py` doit avoir son fichier.

## Export CSV

Lien « ⬇ Exporter en CSV » en haut de la collection (`/u/<pseudo>/export.csv`) : une ligne
par shiny, avec les filtres et le tri en cours. Format pensé pour Excel en français
(séparateur `;`, UTF-8 avec BOM) ; les cellules commençant par `=`, `+`, `-` ou `@` sont
préfixées d'une apostrophe pour ne pas être interprétées comme des formules.
Colonnes : voir `export.py`.

Lien « ⬇ Format tracker » (`/u/<pseudo>/export-tracker.csv`) : même collection au format
du tracker de shiny — sections « Shiny obtenus - <pseudo> » (`Pokémon;Sexe;Surnom;Rencontres;
Méthode;Jeu;Lieu;Charme chroma;Ball;Date d'obtention`), « Shiny manqués » (vide) et
« Shasses en cours » (les chasses du compteur, pour le propriétaire seulement).
La version du jeu est reprise de la note (voir l'import ci-dessous).

## Import CSV

Lien « ⬆ Importer » en haut de sa propre collection (`/import`) :

1. Choisir un fichier CSV — un export du site (les phases sont reconstituées grâce aux
   colonnes `id` et `id_cible`) ou un fichier fait à la main.
2. Un **aperçu** liste les shiny à importer, les doublons ignorés et les lignes en erreur
   (avec la raison). Rien n'est enregistré à cette étape.
3. Confirmer : seules les lignes valides sont importées.

Fichier fait à la main : séparateur `;` ou `,`, UTF-8 ou Windows-1252. Colonnes
obligatoires `n_pokedex` ou `espece`, `jeu`, `methode`, `genre` ; facultatives `forme`,
`surnom`, `date_capture` (AAAA-MM-JJ ou JJ/MM/AAAA), `rencontres`, `poke_ball`, `lieu`,
`charme_chroma` (oui/non), `note`.
Les noms s'écrivent comme sur le site, sans souci d'accents ni de majuscules.
Un doublon = même Pokémon, forme, jeu, genre, date, surnom et rencontres. 4 Mo maximum.
Export du tracker de shiny (comme `6ac41126182b2.csv`) : accepté tel quel. La section
« Shiny obtenus » va dans la collection, « Shasses en cours » dans le compteur (Pokémon, jeu,
méthode, lieu, charme chroma, rencontres et date de début ; doublon =
même Pokémon, forme, jeu et méthode qu'une chasse déjà en cours), « Shiny manqués » est ignorée. Jeux par version (« Violet » → Écarlate / Violet, « Argent Soulsilver » → HeartGold /
SoulSilver…), sexe `A` = asexué (vide = asexué, signalé), heure de la date ignorée, Balls de
Légendes Arceus converties en variantes de Hisui. Lieu et charme chroma vont dans leurs colonnes ;
la version n'ayant pas de colonne sur le site, elle est rangée en tête de la note
(`Version : Violet`) et ressort dans l'export « Format tracker ».
Code dans `importer.py`.

## Statistiques

Page publique `/u/<pseudo>/stats` (lien « 📊 Statistiques » en haut de la collection) :
chiffres clés (shiny, espèces, rencontres totales, moyenne et médiane, phases), captures
par mois ou par année, répartition par famille de jeux, méthode, Poké Ball, tranche de
rencontres et genre, Pokédex shiny par génération, records et espèces favorites.
Chaque graphique a une infobulle au survol et un tableau « Voir les données ».
Calculs dans `stats.py`.

## Compteur

1. Lancer une chasse : Pokémon ciblé, jeu, méthode, et ce qu'on compte : **les rencontres**
   ou **le temps** (timer).
2. Rencontres : gros bouton **+**, ou touches `Espace` / `+` (et `−` pour corriger).
   Le pas est réglable (ex. 5 pour les hordes) ; chaque clic est enregistré immédiatement.
   Timer : bouton **Démarrer / Pause** ou touche `Espace` ; le temps est tenu par le serveur,
   il continue donc page fermée. Il peut être corrigé dans les réglages (H:MM:SS).
3. Un shiny non ciblé apparaît : « Un shiny en phase ! » l'ajoute à la collection
   (jeu, méthode, rencontre en cours ou temps écoulé, date du jour) comme phase de la chasse.
4. La cible apparaît : « shiny trouvé ! » arrête le timer et ouvre la fiche pré-remplie
   (rencontres ou temps de chasse, date, phases) ; l'enregistrer ajoute le shiny à la
   collection et clôt la chasse. Le temps de chasse s'affiche ensuite sur la carte du shiny.

Abandonner une chasse la supprime ; les phases déjà trouvées restent dans la collection.

## Commandes utiles

```powershell
flask --app app create-user <nom>       # crée un utilisateur
flask --app app reset-db                # efface TOUTES les données
```

## Structure

```
app.py                 # routes, accès BDD, authentification
pokemon.py             # jeux, genres, recherche d'espèce, calcul des sprites
methods.py             # méthodes de chasse et taux shiny (lit data/methodes.json)
duration.py            # temps de chasse : saisie et affichage
filters.py             # filtres et tris de la collection
stats.py               # calcul des statistiques
shinydex.py            # Shinydex national et régionaux
export.py              # export CSV de la collection
importer.py            # import CSV (analyse et validation)
data/pokedex_fr.json   # n° Pokédex -> nom français (source : PokeAPI)
data/forms_fr.json     # formes alternatives : noms français et sprites (source : PokeAPI)
data/shinydex/         # Pokédex du Shinydex, modifiables à la main (voir LISEZMOI.md)
data/methodes.json     # méthodes, jeux et taux shiny, modifiable à la main (voir LISEZMOI_methodes.md)
schema.sql             # tables users, shinies, hunt_phases, hunts (compteur)
templates/             # pages HTML (Jinja2)
static/style.css
static/sprites/        # vos sprites, un dossier par jeu (voir static/sprites/LISEZMOI.md)
```

## Production

- Définir `SECRET_KEY` (variable d'environnement) avec une valeur aléatoire :
  `python -c "import secrets; print(secrets.token_hex(32))"`
- Ne pas utiliser `debug=True` ; servir via `waitress` ou `gunicorn`.
