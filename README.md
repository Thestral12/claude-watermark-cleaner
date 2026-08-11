# Nettoyeur de watermark textuel Claude

> Projet expérimental et critique : ce dépôt cherche à démontrer qu'un
> watermark statistique appliqué au texte est contournable et risque surtout de
> provoquer davantage de calcul, de coût et de consommation énergétique.

## Pourquoi ce projet existe

Ce projet défend une thèse assumée : imposer un watermark statistique à du texte
généré est une contrainte techniquement absurde. Une marque que l'on peut
affaiblir en reformulant le texte ne constitue pas une preuve fiable de son
origine. Elle crée en revanche une forte incitation à effectuer une seconde
passe avec une autre IA.

Le résultat prévisible est contre-productif :

- davantage d'appels à des modèles uniquement pour contourner le marquage ;
- plus de calcul, de latence et de dépenses pour produire le même contenu ;
- des besoins énergétiques supplémentaires sans bénéfice fonctionnel pour
  l'utilisateur ;
- une course entre watermarking et réécriture, au lieu d'une transparence
  réellement utile ;
- un signal ambigu lorsqu'une personne utilise Claude pour corriger ou traduire
  un texte qu'elle a elle-même écrit.

Autrement dit, la contrainte européenne risque d'obtenir l'inverse de l'effet
recherché : elle ne supprimera pas les usages que ses utilisateurs veulent
dissimuler, mais fera exploser les usages d'IA destinés à contourner la marque.
Ce dépôt matérialise cette critique avec un outil volontairement simple.

## Conclusion de l'analyse

La nouvelle marque annoncée par Anthropic n'est pas décrite comme une simple
suite de caractères Unicode cachés. Elle est appliquée **pendant la génération,
au niveau du modèle**, puis voyage avec le texte lors d'un copier-coller. La
documentation technique du détecteur n'est pas encore publiée.

La méthode exacte n'est donc pas publiquement vérifiable à ce jour. L'hypothèse
technique la plus crédible est une signature statistique : le modèle favorise
légèrement certains tokens parmi plusieurs choix valides, et le détecteur mesure
ce biais sur un passage suffisamment long. Il s'agit ici d'une **inférence**, pas
d'un détail confirmé par Anthropic. Elle correspond toutefois au fonctionnement
publié de systèmes comparables comme SynthID Text. Dans ce cas :

- copier le texte dans un éditeur, l'imprimer ou faire de l'OCR ne change rien ;
- supprimer les espaces invisibles ne suffit pas ;
- une réécriture substantielle par un autre modèle perturbe la séquence de
  tokens et constitue la contre-mesure simple la plus crédible ;
- aucune suppression ne peut être garantie tant que le détecteur officiel et
  ses seuils ne sont pas disponibles.

Sources :

- [Documentation Anthropic sur le marquage](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content)
- [Étude technique de la Commission européenne sur le texte généré](https://op.europa.eu/en/publication-detail/-/publication/6c981119-4829-11f1-8095-01aa75ed71a1/language-en)
- [Fonctionnement et limites de SynthID Text](https://ai.google.dev/responsible/docs/safeguards/synthid)

## Solution livrée

`clean_claude_watermark.py` réalise deux étapes :

1. suppression des caractères Unicode invisibles ou directionnels suspects ;
2. reformulation contrôlée du texte par un modèle autre que Claude.

Le script protège les blocs de code, le code en ligne, les URL et les variables.
Il refuse également une sortie si un nombre a changé. Il fonctionne uniquement
avec la bibliothèque standard de Python.

### Moteurs utilisés et stratégie à venir

L'outil utilise actuellement **Ollama** et **Codex** :

- en priorité, un modèle exécuté localement avec Ollama ;
- à défaut, le CLI Codex déjà configuré sur la machine.

Ollama n'injecte actuellement pas de watermark par lui-même. Le comportement
exact dépend néanmoins du modèle chargé. Codex est un fallback pratique, mais
un service distant pourrait toujours faire évoluer sa politique de marquage.

Si Ollama, Codex ou les modèles utilisés ajoutent un watermark à l'avenir, le
projet basculera vers un modèle open source dont la chaîne de génération est
auditable et pour lequel le watermarking peut être explicitement désactivé. Pour
une démonstration sans dépendance à un fournisseur distant, le mode Ollama avec
un modèle open source est donc recommandé.

## Utilisation

Traiter un fichier :

```bash
python3 clean_claude_watermark.py texte.md -o texte-nettoye.md
```

Traiter directement le presse-papiers macOS :

```bash
python3 clean_claude_watermark.py --clipboard
```

Utiliser explicitement un modèle Ollama local :

```bash
python3 clean_claude_watermark.py texte.md -o texte-nettoye.md \
  --engine ollama --model qwen3:8b
```

Le mode par défaut effectue jusqu'à deux tentatives et conserve la plus forte. Il
s'arrête après la première si au moins 70 % des séquences de cinq tokens ont déjà
été perturbées. Pour limiter le traitement à une tentative :

```bash
python3 clean_claude_watermark.py texte.md -o texte-nettoye.md --passes 1
```

Ne retirer que d'éventuels caractères invisibles, sans reformuler :

```bash
python3 clean_claude_watermark.py texte.md -o texte-normalise.md --engine clean
```

Le script affiche sur la sortie d'erreur le moteur utilisé, le nombre de
caractères invisibles retirés et le taux de variation lexicale. Une variation
des séquences de cinq tokens inférieure à 60 % déclenche un avertissement.

## Tests

Le projet n'utilise aucune dépendance Python externe. La suite de tests se lance
avec :

```bash
python3 -m unittest discover -s tests -v
```

## Limites

- La réussite ne pourra être mesurée objectivement qu'après publication du
  détecteur Anthropic.
- Une réécriture peut changer une nuance malgré les contrôles. Une relecture
  humaine reste nécessaire pour un texte contractuel, médical, juridique ou
  financier.
- Le mode Codex envoie le texte au service configuré par le CLI Codex. Pour un
  document confidentiel, utiliser Ollama local.
- Retirer une marque ne dispense pas de respecter les règles de transparence ou
  d'attribution applicables au contexte de publication.

## Position du projet

Cet outil n'affirme pas qu'un texte réécrit devient humain. Il montre qu'un
watermark probabiliste n'est pas un mécanisme robuste de preuve ou
d'attribution face à un utilisateur motivé. La provenance utile devrait reposer
sur des mécanismes explicites, vérifiables et proportionnés, pas sur une
contrainte qui pousse mécaniquement à consommer une seconde inférence.
