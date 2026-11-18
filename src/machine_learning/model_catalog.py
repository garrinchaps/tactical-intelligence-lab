"""Catálogo público e honesto dos modelos do laboratório."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ModelCard:
    id: str
    name: str
    pillar: str
    task: str
    status: str
    implementation: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    metrics: tuple[str, ...]
    limitations: tuple[str, ...]
    version: str = "unversioned"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["inputs"] = list(self.inputs)
        value["outputs"] = list(self.outputs)
        value["metrics"] = list(self.metrics)
        value["limitations"] = list(self.limitations)
        return value


def model_cards() -> list[dict[str, Any]]:
    cards = [
        ModelCard(
            "lab-ai-analyst", "IA do laboratório — analista dados→texto", "NLP / ML supervisionado",
            "seleção de conteúdo + geração de texto", "implementado-treinável",
            "src/intelligence/lab_ai/",
            ("estatísticas do time", "números por jogador", "lances com coordenadas", "régua de milhares de jogos"),
            ("resposta em texto", "relatório completo", "plano para explorar/corrigir"),
            ("log-loss no teste por resposta avaliada", "promoção só com melhora"),
            ("só aprende com respostas avaliadas (👍/👎)", "não vê vídeo: sem postura corporal nem posicionamento sem bola"),
            "selector-v000+",
        ),
        ModelCard(
            "lineup-genetic", "Escalação por algoritmo genético", "Computação evolucionária",
            "otimização combinatória", "implementado",
            "src/squad/genetic.py",
            ("elenco com nota e posição", "formação", "fraquezas do rival", "perfil relativo do atleta"),
            ("XI com aptidão", "mudanças contra o melhor XI húngaro", "porquê de cada bônus"),
            ("aptidão completa vs baseline húngaro", "curva de convergência", "semente reprodutível"),
            ("bônus depende de fraquezas medidas nos últimos jogos", "perfil relativo ao próprio elenco"),
            "ga-v1",
        ),
        ModelCard(
            "possession-danger-xgb", "Perigo da posse — XGBoost", "ML supervisionado",
            "classificação binária", "implementado-experimental",
            "src/machine_learning/supervised.py",
            ("cadeias de posse", "posição inicial", "progressão", "pressão"),
            ("probabilidade de perigo",),
            ("ROC-AUC", "F1", "Brier", "precisão", "recall"),
            ("split legado ainda pode ser GroupShuffleSplit; avaliação temporal em migração",),
        ),
        ModelCard(
            "possession-danger-mlp", "Perigo da posse — MLP NumPy", "Redes neurais",
            "classificação binária", "implementado-experimental",
            "src/machine_learning/neural_net.py",
            ("features do danger dataset",),
            ("probabilidade de perigo",),
            ("ROC-AUC", "log-loss", "Brier", "ECE"),
            ("não é modelo de visão; requer avaliação temporal antes de produção",),
        ),
        ModelCard(
            "player-behavior-clusters", "Perfis comportamentais", "ML não supervisionado",
            "clustering", "implementado-experimental",
            "src/machine_learning/clustering.py",
            ("métricas normalizadas por 90",),
            ("cluster e centróide",),
            ("silhouette", "estabilidade", "tamanho mínimo"),
            ("rótulos táticos exigem interpretação e não são posições oficiais",),
        ),
        ModelCard(
            "tactical-report-guard", "Guardrail de relatórios", "Sistemas especialistas",
            "verificação de evidências", "implementado",
            "src/reports/report_builder.py; src/guard/",
            ("evidências e texto",),
            ("classificação de rastreabilidade",),
            ("números não rastreáveis", "taxa de cobertura"),
            ("não avalia causalidade nem substitui revisão humana",),
        ),
        ModelCard(
            "squad-planner-rules", "Compatibilidade de elenco", "Sistemas especialistas",
            "otimização/regras", "implementado",
            "src/squad/planner.py",
            ("posições", "fit", "restrições do elenco"),
            ("plano e provável XI",),
            ("fitness", "violações", "cobertura de regras"),
            ("a versão atual não deve ser chamada de algoritmo genético",),
        ),
        ModelCard(
            "player-rating-mamdani", "Contribuição tática fuzzy", "Lógica fuzzy Mamdani",
            "avaliação interpretável", "implementado-experimental",
            "src/intelligence/fuzzy.py",
            ("intensidade defensiva", "precisão de passe"),
            ("índice fuzzy 0–100", "regras ativadas", "pertinências"),
            ("cobertura de regras", "monotonicidade", "sensibilidade"),
            ("grau fuzzy não é probabilidade; entradas precisam de normalização semântica",),
        ),
        ModelCard(
            "match-pressure-sugeno", "Pressão territorial", "Takagi–Sugeno",
            "indicador contínuo", "implementado-experimental",
            "src/intelligence/fuzzy.py",
            ("posse", "entradas territoriais", "finalizações", "minuto"),
            ("índice de pressão 0–100", "pesos das regras"),
            ("latência", "estabilidade em replay", "correlação retrospectiva"),
            ("não estima probabilidade de gol nem causalidade",),
        ),
    ]
    return [card.to_dict() for card in cards]
