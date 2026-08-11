#!/usr/bin/env python3
"""Nettoie puis reformule un texte afin de perturber un watermark statistique.

Le script fonctionne sans dependance Python externe. Il prefere un modele Ollama
local lorsqu'il en trouve un, puis utilise le CLI Codex deja installe. Le mode
"clean" se limite au nettoyage Unicode et ne peut pas retirer un watermark
fonde sur le choix des mots.
"""

from __future__ import annotations

import argparse
from collections import Counter
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request


VERSION = "1.0.0"

# Caracteres invisibles couramment utilises par les watermarks Unicode, les
# balises furtives et les attaques de texte bidirectionnel. Les separateurs
# Unicode visibles comme des espaces sont traites separement.
SUSPICIOUS_RANGES = (
    (0x00AD, 0x00AD),  # soft hyphen
    (0x034F, 0x034F),  # combining grapheme joiner
    (0x061C, 0x061C),  # Arabic letter mark
    (0x115F, 0x1160),  # Hangul fillers
    (0x17B4, 0x17B5),  # Khmer inherent vowels
    (0x180B, 0x180F),  # Mongolian selectors / separator
    (0x200B, 0x200F),  # zero-width and direction marks
    (0x202A, 0x202E),  # bidi embeddings / overrides
    (0x2060, 0x206F),  # word joiner and bidi isolates
    (0x3164, 0x3164),  # Hangul filler
    (0xFEFF, 0xFEFF),  # zero-width no-break space / BOM
    (0xFFF9, 0xFFFB),  # interlinear annotation controls
    (0xE0000, 0xE007F),  # Unicode tags
)

LOCK_RE = re.compile(
    r"(^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$)"  # fenced code
    r"|(`+[^`\n]*?`+)"  # inline code
    r"|(https?://[^\s<>\]\)]+)"  # URL
    r"|(mailto:[^\s<>\]\)]+)"
    r"|(\$\{[^{}\n]+\}|\{\{[^{}\n]+\}\}|%\([^)]+\)[#0 +\-]?[0-9.*]*[a-zA-Z])",
    re.MULTILINE | re.DOTALL,
)

WORD_RE = re.compile(r"\w+", re.UNICODE)


def is_suspicious(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in SUSPICIOUS_RANGES)


def sanitize_unicode(text: str) -> tuple[str, list[dict[str, object]]]:
    """Supprime les marqueurs invisibles et uniformise les espaces Unicode."""
    removed: dict[tuple[int, str], int] = {}
    output: list[str] = []

    for character in text:
        if is_suspicious(character):
            key = (ord(character), unicodedata.name(character, "UNKNOWN"))
            removed[key] = removed.get(key, 0) + 1
            continue

        # Tous les separateurs horizontaux deviennent un espace ASCII. Les
        # retours de ligne restent intacts pour preserver Markdown et le texte.
        if unicodedata.category(character) == "Zs":
            output.append(" ")
        else:
            output.append(character)

    cleaned = unicodedata.normalize("NFC", "".join(output))
    report = [
        {"codepoint": f"U+{codepoint:04X}", "name": name, "count": count}
        for (codepoint, name), count in sorted(removed.items())
    ]
    return cleaned, report


def protect_literals(text: str) -> tuple[str, dict[str, str]]:
    """Masque le code, les URL et les variables avant reformulation."""
    protected: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"ZXQLOCK{len(protected):06d}QXZ"
        protected[token] = match.group(0)
        return token

    return LOCK_RE.sub(replace, text), protected


def restore_literals(text: str, protected: dict[str, str]) -> str:
    missing = [token for token in protected if token not in text]
    if missing:
        raise RuntimeError(
            "La reformulation a modifie des blocs proteges "
            f"({', '.join(missing[:3])}). Sortie refusee pour eviter une corruption."
        )
    restored = text
    for token, literal in protected.items():
        restored = restored.replace(token, literal)
    return restored


def prompt_for(text: str, pass_number: int) -> str:
    extra = (
        "Il s'agit d'une nouvelle tentative, volontairement plus forte. "
        "Reconstruis chaque phrase depuis son sens au lieu de corriger la phrase "
        "existante. Change chaque structure de phrase et ne conserve aucune suite "
        "de quatre mots lexicaux dans le meme ordre, sauf nom propre ou element "
        "ZXQLOCK...QXZ."
        if pass_number > 1
        else ""
    )
    return f"""Tu es un editeur de texte. Reformule le texte place entre les balises INPUT.

Objectif : perturber fortement toute signature statistique fondee sur le choix et
l'enchainement des tokens, sans modifier l'information transmise.

Contraintes obligatoires :
- rends uniquement le texte final, sans preambule, commentaire ni balise INPUT ;
- conserve exactement le sens, les faits, le niveau de certitude et le ton ;
- n'ajoute et ne retire aucune information ;
- change reellement la syntaxe, l'ordre interne des propositions et le vocabulaire
  du texte courant ; vise au moins 35 % de tokens differents ;
- conserve la langue de chaque passage ;
- conserve les titres, listes, paragraphes et tableaux Markdown ;
- recopie absolument a l'identique tous les identifiants ZXQLOCK...QXZ ;
- conserve exactement tous les nombres, noms propres et references.
{extra}

<INPUT>
{text}
</INPUT>"""


def ollama_models() -> list[str]:
    try:
        request = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return [item["name"] for item in payload.get("models", []) if item.get("name")]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError):
        return []


def rewrite_with_ollama(text: str, model: str | None, pass_number: int) -> str:
    available = ollama_models()
    selected = model or (available[0] if available else None)
    if not selected:
        raise RuntimeError(
            "Ollama ne fournit aucun modele local. Installez un modele, par exemple "
            "avec `ollama pull qwen3:8b`, ou utilisez --engine codex."
        )

    payload = json.dumps(
        {
            "model": selected,
            "prompt": prompt_for(text, pass_number),
            "stream": False,
            "options": {"temperature": 0.7},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            result = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Echec de la reformulation Ollama : {error}") from error
    return str(result.get("response", "")).strip()


def rewrite_with_codex(text: str, model: str | None, pass_number: int) -> str:
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("Le CLI Codex est introuvable. Utilisez Ollama ou --engine clean.")

    with tempfile.TemporaryDirectory(prefix="watermark-cleaner-") as temp_dir:
        result_file = Path(temp_dir) / "result.txt"
        def execute(selected_model: str | None) -> subprocess.CompletedProcess[str]:
            command = [
                executable,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--cd",
                temp_dir,
                "--output-last-message",
                str(result_file),
            ]
            if selected_model:
                command.extend(["--model", selected_model])
            command.append("-")
            return subprocess.run(
                command,
                input=prompt_for(text, pass_number),
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=900,
                check=False,
            )

        completed = execute(model)
        # Une configuration Codex recente peut pointer vers un modele que le CLI
        # local, plus ancien, ne reconnait pas encore. Le modele de repli garde le
        # mode automatique utilisable sans modifier la configuration de l'usager.
        if (
            model is None
            and completed.returncode != 0
            and "requires a newer version of Codex" in completed.stderr
        ):
            result_file.unlink(missing_ok=True)
            completed = execute("gpt-5.4")

        if completed.returncode != 0 or not result_file.exists():
            detail = completed.stderr.strip().splitlines()
            reason = detail[-1] if detail else f"code {completed.returncode}"
            raise RuntimeError(f"Echec de la reformulation Codex : {reason}")
        return result_file.read_text(encoding="utf-8").strip()


def lexical_change(before: str, after: str) -> float:
    left = [word.casefold() for word in WORD_RE.findall(before)]
    right = [word.casefold() for word in WORD_RE.findall(after)]
    if not left and not right:
        return 0.0
    similarity = difflib.SequenceMatcher(a=left, b=right, autojunk=False).ratio()
    return 1.0 - similarity


def sequence_disruption(before: str, after: str, size: int = 5) -> float:
    """Mesure la part des sequences de tokens qui ne survivent pas a l'edition."""
    left = [word.casefold() for word in WORD_RE.findall(before)]
    right = [word.casefold() for word in WORD_RE.findall(after)]
    if len(left) < size:
        return lexical_change(before, after)
    left_ngrams = Counter(tuple(left[index : index + size]) for index in range(len(left) - size + 1))
    right_ngrams = Counter(
        tuple(right[index : index + size]) for index in range(len(right) - size + 1)
    )
    surviving = sum((left_ngrams & right_ngrams).values())
    return 1.0 - (surviving / sum(left_ngrams.values()))


def numeric_tokens(text: str) -> list[str]:
    tokens = re.findall(r"(?<!\w)[+\-]?\d[\d.,:/]*(?:\s*%)?(?!\w)", text)
    return [re.sub(r"\s+", "", token) for token in tokens]


def choose_engine(requested: str) -> str:
    if requested != "auto":
        return requested
    if ollama_models():
        return "ollama"
    if shutil.which("codex"):
        return "codex"
    return "clean"


def rewrite(
    text: str, engine: str, model: str | None, passes: int
) -> tuple[str, float, float]:
    masked, protected = protect_literals(text)
    best = masked
    best_disruption = -1.0
    for pass_number in range(1, passes + 1):
        if engine == "ollama":
            candidate = rewrite_with_ollama(masked, model, pass_number)
        elif engine == "codex":
            candidate = rewrite_with_codex(masked, model, pass_number)
        else:
            raise ValueError(f"Moteur de reformulation inconnu : {engine}")
        candidate_disruption = sequence_disruption(masked, candidate)
        if candidate_disruption > best_disruption:
            best = candidate
            best_disruption = candidate_disruption
        # Deuxieme appel inutile lorsqu'une premiere reformulation perturbe deja
        # les n-grammes a un niveau eleve.
        if best_disruption >= 0.70:
            break

    restored = restore_literals(best, protected)
    if text.strip():
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()) :]
        restored = leading + restored.strip() + trailing
    before_numbers = numeric_tokens(text)
    after_numbers = numeric_tokens(restored)
    if before_numbers != after_numbers:
        raise RuntimeError(
            "La reformulation a modifie un nombre ou son ordre. Sortie refusee "
            "pour proteger l'integrite factuelle."
        )
    return restored, lexical_change(text, restored), sequence_disruption(text, restored)


def read_input(path: str | None, clipboard: bool) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    if clipboard:
        completed = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError("Impossible de lire le presse-papiers macOS.")
        return completed.stdout
    if sys.stdin.isatty():
        raise RuntimeError("Indiquez un fichier, --clipboard, ou envoyez le texte sur stdin.")
    return sys.stdin.read()


def write_output(text: str, path: str | None, clipboard: bool, force: bool) -> None:
    if clipboard:
        completed = subprocess.run(
            ["pbcopy"], input=text, text=True, check=False
        )
        if completed.returncode != 0:
            raise RuntimeError("Impossible d'ecrire dans le presse-papiers macOS.")
        return
    if path:
        destination = Path(path)
        if destination.exists() and not force:
            raise RuntimeError(
                f"Le fichier existe deja : {destination}. Ajoutez --force pour le remplacer."
            )
        destination.write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Nettoie les caracteres invisibles puis reformule un texte pour "
            "perturber un watermark statistique de Claude."
        )
    )
    parser.add_argument("input", nargs="?", help="fichier UTF-8 a traiter")
    parser.add_argument("-o", "--output", help="fichier de sortie")
    parser.add_argument(
        "--engine",
        choices=("auto", "ollama", "codex", "clean"),
        default="auto",
        help="auto prefere Ollama local, puis Codex (defaut: auto)",
    )
    parser.add_argument("--model", help="modele Ollama ou Codex a utiliser")
    parser.add_argument(
        "--passes",
        type=int,
        choices=(1, 2),
        default=2,
        help="nombre maximal de tentatives; arret anticipe si le resultat est fort (defaut: 2)",
    )
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="lit puis remplace le contenu du presse-papiers macOS",
    )
    parser.add_argument(
        "--force", action="store_true", help="autorise le remplacement du fichier de sortie"
    )
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.clipboard and (args.input or args.output):
        parser.error("--clipboard ne se combine pas avec un fichier d'entree ou de sortie")

    try:
        original = read_input(args.input, args.clipboard)
        cleaned, removed = sanitize_unicode(original)
        engine = choose_engine(args.engine)
        final = cleaned
        change = 0.0
        disruption = 0.0
        if engine != "clean":
            final, change, disruption = rewrite(cleaned, engine, args.model, args.passes)
        write_output(final, args.output, args.clipboard, args.force)

        removed_count = sum(int(item["count"]) for item in removed)
        print(
            f"Moteur: {engine} | caracteres invisibles retires: {removed_count} | "
            f"variation lexicale: {change:.0%} | rupture des sequences: {disruption:.0%}",
            file=sys.stderr,
        )
        if engine == "clean":
            print(
                "Attention: le nettoyage Unicode seul ne retire pas un watermark "
                "statistique fonde sur le choix des mots.",
                file=sys.stderr,
            )
        elif disruption < 0.60:
            print(
                "Attention: moins de 60 % des sequences de 5 tokens ont ete "
                "perturbees. Une relecture et une edition manuelle sont conseillees.",
                file=sys.stderr,
            )
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Erreur: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
