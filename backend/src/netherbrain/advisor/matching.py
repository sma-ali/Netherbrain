"""Retrouver un modèle dans les benchmarks, malgré des noms écrits différemment.

« qwen3.5:9b » chez Ollama, « qwen/qwen3.5-9b:free » chez OpenRouter et « Qwen3.5 9B » chez
Artificial Analysis désignent le même modèle. On compare leurs « mots » une fois normalisés,
et on préfère ne rien rapprocher plutôt que de rapprocher le mauvais modèle.
"""

import re
from bisect import bisect_left
from dataclasses import dataclass

from netherbrain.advisor.sources import BenchmarkEntry

# Des mots qui ne disent rien de l'identité du modèle.
NOISE = {"instruct", "it", "chat", "latest", "free", "preview", "hf", "gguf"}
# Les suffixes de quantification (q4_k_m, fp16, mxfp4…) : même modèle, autre compression.
QUANTIZATION = re.compile(r"q\d.*|fp\d+|bf\d+|int\d+|mxfp\d+|nvfp\d+|awq|gptq|mlx")
SIZE = re.compile(r"\d+b")
# Artificial Analysis évalue à part les deux modes d'un même modèle : « Qwen3 8B (Reasoning) »
# et « Qwen3 8B (Non-reasoning) ». Ces mots désignent le mode, pas le modèle.
MODE_WORDS = {"reasoning", "non"}
# Un petit modèle local se compare aux modèles ouverts de sa catégorie (ceux qui tiennent sur
# une carte graphique), pas aux géants du cloud : c'est aussi l'échelle de la grille de forces.
SMALL_MODEL_MAX_B = 35
# En dessous, la catégorie compte trop peu de modèles : le percentile ne voudrait rien dire.
MIN_SMALL_POPULATION = 20
METRICS = ("intelligence", "coding", "math")
# En dessous, le rapprochement est trop hasardeux (« Qwen 14B » pour « Qwen 14B VL Math… »).
MIN_SIMILARITY = 0.4


def words(name: str) -> list[str]:
    """Les mots d'un nom de modèle : sans éditeur, sans bruit, sans quantification."""
    text = name.lower().rsplit("/", 1)[-1]  # « qwen/qwen3.5-9b » → « qwen3.5-9b »
    result: list[str] = []
    for part in re.split(r"[^a-z0-9_]+", text):
        if not part or part in NOISE or QUANTIZATION.fullmatch(part):
            continue
        # « Gemma 4 » et « gemma4 » : un nombre seul se recolle au mot qui le précède.
        if part.isdigit() and result and result[-1][-1].isalpha():
            result[-1] += part
        else:
            result.append(part)
    return result


def size_of(model_words: list[str]) -> str | None:
    return next((word for word in model_words if SIZE.fullmatch(word)), None)


def billions(model_words: list[str]) -> float | None:
    """Les milliards de paramètres écrits dans le nom (« 14b » → 14), s'ils y figurent."""
    size = size_of(model_words)
    return float(size[:-1]) if size else None


@dataclass(frozen=True)
class BenchmarkMatch:
    # Le modèle retrouvé, tel que le nomme la source.
    name: str
    # Pour chaque indice, la part des modèles évalués qu'il dépasse (de 0 à 1).
    percentiles: dict[str, float]
    output_speed: float | None
    # True : comparé aux seuls modèles ouverts de sa catégorie (jusqu'à SMALL_MODEL_MAX_B).
    small: bool = False


class BenchmarkIndex:
    """Les benchmarks prêts à être interrogés : rapprochement des noms, et percentiles."""

    def __init__(self, entries: list[BenchmarkEntry]) -> None:
        self._entries = [(entry, words(entry.slug), words(entry.name)) for entry in entries]
        small = [
            entry
            for entry, *spellings in self._entries
            if any((b := billions(s)) is not None and b <= SMALL_MODEL_MAX_B for s in spellings)
        ]
        self._values = {
            population: {
                metric: sorted(v for e in group if (v := getattr(e, metric)) is not None)
                for metric in METRICS
            }
            for population, group in (("all", entries), ("small", small))
        }
        self._small_count = len(small)

    def __len__(self) -> int:
        return len(self._entries)

    def match(
        self, model_id: str, reasoning: bool | None = None, small: bool = False
    ) -> BenchmarkMatch | None:
        """Le benchmark du modèle, ou None. `reasoning` : le modèle installé réfléchit-il ?
        `small` : un modèle local, à comparer aux modèles de sa catégorie.

        Quand la source évalue ses deux modes, on retient celui qui correspond au modèle
        installé ; sans l'information, le mode le mieux noté.
        """
        mine = words(model_id)
        if len(mine) < 2:
            return None  # « qwen3 » seul : trop vague pour savoir de quelle taille il s'agit
        wanted = set(mine) - MODE_WORDS

        best: BenchmarkEntry | None = None
        best_score = 0.0
        for entry, *spellings in self._entries:
            similarity = max(
                (self._similarity(mine[0], wanted, theirs) for theirs in spellings), default=0.0
            )
            if similarity < MIN_SIMILARITY:
                continue
            score = similarity + (
                0.25 if reasoning is not None and _mode(entry, spellings) == reasoning else 0.0
            )
            better = score > best_score or (
                score == best_score
                and best is not None
                and (entry.intelligence or 0) > (best.intelligence or 0)
            )
            if better:
                best, best_score = entry, score

        if best is None:
            return None
        population = "small" if small and self._small_count >= MIN_SMALL_POPULATION else "all"
        return BenchmarkMatch(
            name=best.name,
            percentiles={
                metric: self.percentile(metric, value, population)
                for metric in METRICS
                if (value := getattr(best, metric)) is not None
            },
            output_speed=best.output_speed,
            small=population == "small",
        )

    @staticmethod
    def _similarity(family: str, wanted: set[str], theirs: list[str]) -> float:
        """0 si ce n'est pas le même modèle ; sinon, la part de leurs mots que l'on retrouve.

        Même famille (premier mot), et tous nos mots présents chez eux : « qwen3 8b » se
        retrouve dans « Qwen3 VL 8B » (moins bien que dans « Qwen3 8B »), jamais dans « Qwen3 14B ».
        """
        core = set(theirs) - MODE_WORDS
        if not theirs or theirs[0] != family or not wanted <= core:
            return 0.0
        return len(wanted) / len(core)

    def percentile(self, metric: str, value: float, population: str = "all") -> float:
        """La part des modèles évalués (tous, ou ceux de la catégorie) au score inférieur."""
        values = self._values[population][metric]
        return bisect_left(values, value) / len(values) if values else 0.0


def _mode(entry: BenchmarkEntry, spellings: list[list[str]]) -> bool | None:
    """True pour le mode qui réfléchit, False pour l'autre, None si la source ne précise pas."""
    for spelling in spellings:
        if "reasoning" in spelling:
            return "non" not in spelling
    return None
