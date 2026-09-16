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


@dataclass(frozen=True)
class BenchmarkMatch:
    # Le modèle retrouvé, tel que le nomme la source.
    name: str
    # Pour chaque indice, la part des modèles évalués qu'il dépasse (de 0 à 1).
    percentiles: dict[str, float]
    output_speed: float | None


class BenchmarkIndex:
    """Les benchmarks prêts à être interrogés : rapprochement des noms, et percentiles."""

    def __init__(self, entries: list[BenchmarkEntry]) -> None:
        self._entries = [(entry, words(entry.slug), words(entry.name)) for entry in entries]
        self._values = {
            metric: sorted(v for e in entries if (v := getattr(e, metric)) is not None)
            for metric in METRICS
        }

    def __len__(self) -> int:
        return len(self._entries)

    def match(self, model_id: str) -> BenchmarkMatch | None:
        mine = words(model_id)
        if len(mine) < 2:
            return None  # « qwen3 » seul : trop vague pour savoir de quelle taille il s'agit
        wanted = set(mine)

        best: BenchmarkEntry | None = None
        best_similarity = 0.0
        for entry, *spellings in self._entries:
            for theirs in spellings:
                # Même famille (premier mot), et tous nos mots présents chez eux : « qwen3 8b »
                # se retrouve dans « Qwen3 VL 8B », mais jamais dans « Qwen3 14B ».
                if not theirs or theirs[0] != mine[0] or not wanted <= set(theirs):
                    continue
                similarity = len(wanted) / len(set(theirs))
                better = similarity > best_similarity or (
                    similarity == best_similarity
                    and best is not None
                    and (entry.intelligence or 0) > (best.intelligence or 0)
                )
                if better:
                    best, best_similarity = entry, similarity

        if best is None or best_similarity < MIN_SIMILARITY:
            return None
        return BenchmarkMatch(
            name=best.name,
            percentiles={
                metric: self.percentile(metric, value)
                for metric in METRICS
                if (value := getattr(best, metric)) is not None
            },
            output_speed=best.output_speed,
        )

    def percentile(self, metric: str, value: float) -> float:
        """La part des modèles évalués qui ont un score strictement inférieur."""
        values = self._values[metric]
        return bisect_left(values, value) / len(values) if values else 0.0
