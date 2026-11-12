# Démo Tricolor AI — 4 approches dessinables

Lancer une interface **CustomTkinter** permettant de charger une vidéo, dessiner quatre **zones d'entrée** et quatre **zones de sortie** (N/S/E/O), puis compter les véhicules suivis par YOLO + Supervision ByteTrack. Le tableau de bord présente, par direction, les **véhicules présents**, une **estimation visuelle de l'attente à l'arrêt**, les **véhicules sortis**, ainsi qu'une **matrice de flux entrée → sortie** de 4×4.

## Installation

Python 3.10+ :

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Le modèle `yolo11n.pt` peut être téléchargé automatiquement au premier usage. Pour un test totalement hors ligne, renseigner son chemin local dans le champ YOLO.

## Utilisation

1. Ouvrir une vidéo à l'aide du bouton.
2. Choisir `N` puis `in`, cliquer au moins trois points sur l'image et choisir **Terminer polygone** ; recommencer avec `N/out`.
3. Répéter pour `S, E, O` (huit polygones au total, comme les quatre paires entrée/sortie dans l'exemple Roboflow).
4. Cliquer sur **Sauver** pour conserver les coordonnées, puis sur **Démarrer**.
5. Lire la matrice : le nombre de la cellule `N → E` correspond aux ID vus successivement dans la zone entrée N puis dans la sortie E.

Les directions doivent être associées **aux voies réelles**, pas à la position haut/bas dans l'image. La mesure `Présents` est instantanée ; la matrice et `Sortis` sont cumulés. **Attente** est une estimation basée sur le déplacement des boîtes en pixels par seconde, pas un temps d'attente calibré ou une mesure de vitesse réelle. Le suivi peut être imparfait en cas d'occlusions. Ne pas connecter cette démo aux feux réels.

Sources : [Roboflow Traffic Analysis](https://github.com/roboflow/supervision/blob/develop/examples/traffic_analysis/ultralytics_example.py) · [CustomTkinter](https://customtkinter.tomschimansky.com/documentation/) · [Supervision](https://supervision.roboflow.com/latest/).
