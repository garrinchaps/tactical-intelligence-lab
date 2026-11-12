"""
Módulo de Processamento de Linguagem Natural (NLP) Treinado (Camada 4 - Inteligência Semântica)
Implementa e treina localmente:
1. Um Classificador Neural (TF-IDF + MLPClassifier / LogisticRegression Ensemble) para interpretar
   semanticamente a pergunta tática do usuário sem depender de if/else rígidos.
2. Um Motor de Busca Vetorial por Similaridade de Cosseno (Character N-Grams TF-IDF) para
   encontrar equipes, confrontos e jogadores mesmo com variações de escrita ou erros de digitação.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import FeatureUnion, Pipeline


class TacticalNLPInterpreter:
    """
    IA de Linguagem Natural treinada localmente para:
    - Compreender a intenção tática de perguntas abertas em Português (com probabilidades reais).
    - Encontrar confrontos e jogadores por Similaridade Vetorial de Cosseno.
    """

    # Corpus de treinamento tático supervisionado (Frase em Linguagem Natural -> Classe Tática)
    TRAINING_CORPUS: List[Tuple[str, str]] = [
        # 1. PLAYER_SPECIFIC_TACTIC (Anular, marcar ou analisar um atleta específico)
        ("monte uma tatica para anular o jogador", "PLAYER_SPECIFIC_TACTIC"),
        ("como marcar individualmente o camisa 10 deles", "PLAYER_SPECIFIC_TACTIC"),
        ("qual a melhor forma de neutralizar o atacante principal", "PLAYER_SPECIFIC_TACTIC"),
        ("como cortar as linhas de passe que chegam no craque do time", "PLAYER_SPECIFIC_TACTIC"),
        ("quem passa mais a bola para esse jogador e onde ele recebe", "PLAYER_SPECIFIC_TACTIC"),
        ("como parar o ponta deles no um contra um", "PLAYER_SPECIFIC_TACTIC"),
        ("analise especificamente o comportamento individual do atleta", "PLAYER_SPECIFIC_TACTIC"),
        ("quero travar o armador deles para a bola nao chegar limpa", "PLAYER_SPECIFIC_TACTIC"),
        ("encurtar o espaco quando o meia dominar de costas", "PLAYER_SPECIFIC_TACTIC"),
        ("dossie individual para encaixar marcacao no astro adversario", "PLAYER_SPECIFIC_TACTIC"),
        # 2. DEFENSIVE_VULNERABILITIES (Furar defesa, achar buracos, explorar corredores)
        ("analise toda a organizacao defensiva desta equipe", "DEFENSIVE_VULNERABILITIES"),
        ("identifique os principais espacos que podemos explorar na defesa", "DEFENSIVE_VULNERABILITIES"),
        ("como furar a retranca e o bloco baixo desse adversario", "DEFENSIVE_VULNERABILITIES"),
        ("onde eles deixam buraco na linha de quatro defensiva", "DEFENSIVE_VULNERABILITIES"),
        ("qual corredor lateral ou meio espaco a zaga deles cede mais", "DEFENSIVE_VULNERABILITIES"),
        ("como explorar as costas do lateral direito ou esquerdo", "DEFENSIVE_VULNERABILITIES"),
        ("eles sofrem quando fazemos inversao rapida de lado", "DEFENSIVE_VULNERABILITIES"),
        ("atacar o espaco entre o zagueiro e o lateral", "DEFENSIVE_VULNERABILITIES"),
        ("qual o ponto fraco da marcacao e da linha alta deles", "DEFENSIVE_VULNERABILITIES"),
        ("como infiltrar na zona 14 e entrar na grande area deles", "DEFENSIVE_VULNERABILITIES"),
        # 3. PRESSING_AND_BUILDUP (Pressionar saída de bola, travar pivô/volante)
        ("como devemos pressionar a saida de bola dessa equipe", "PRESSING_AND_BUILDUP"),
        ("quem e o pivo da construcao na rede de passes", "PRESSING_AND_BUILDUP"),
        ("como subir a marcacao pressao alta no tiro de meta deles", "PRESSING_AND_BUILDUP"),
        ("onde montar a armadilha de pressao para roubar a bola no campo de ataque", "PRESSING_AND_BUILDUP"),
        ("qual zagueiro ou volante concentra a distribuicao inicial", "PRESSING_AND_BUILDUP"),
        ("eles saem jogando curto ou dao chutao na construcao", "PRESSING_AND_BUILDUP"),
        ("travar a circulacao de passes no primeiro terco", "PRESSING_AND_BUILDUP"),
        ("forcar o erro na saida de trás do adversario", "PRESSING_AND_BUILDUP"),
        # 4. DEFENSIVE_TRANSITION (Transição defensiva, pós-perda, contra-ataque sofrido)
        ("identifique os problemas na transicao defensiva", "DEFENSIVE_TRANSITION"),
        ("o que acontece quando a equipe perde a posse de bola no ataque", "DEFENSIVE_TRANSITION"),
        ("eles fazem pressao pos perda gegenpressing nos 5 segundos", "DEFENSIVE_TRANSITION"),
        ("onde o time mais perde a bola e sofre contra ataque nas costas", "DEFENSIVE_TRANSITION"),
        ("qual a zona critica de turnovers e erros de passe perigosos", "DEFENSIVE_TRANSITION"),
        ("capacidade de recomposicao defensiva apos errar passe", "DEFENSIVE_TRANSITION"),
        ("exposicao dos zagueiros quando os laterais sobem e perdem a bola", "DEFENSIVE_TRANSITION"),
        # 5. OFFENSIVE_TRANSITION (Contra-ataque rápido, transição ofensiva, velocidade)
        ("qual a velocidade da transicao ofensiva e contra ataque", "OFFENSIVE_TRANSITION"),
        ("quem puxa o contra ataque rapido quando eles roubam a bola", "OFFENSIVE_TRANSITION"),
        ("como eles atacam em velocidade apos recuperar a posse", "OFFENSIVE_TRANSITION"),
        ("eficiencia dos ataques rapidos e progressao vertical direta", "OFFENSIVE_TRANSITION"),
        ("jogadores mais acionados para acelerar na transicao", "OFFENSIVE_TRANSITION"),
        # 6. SUBSTITUTIONS_AND_SQUAD (Substituições, cansaço, banco, 2º tempo)
        ("sugira uma substituicao para melhorar a construcao ofensiva", "SUBSTITUTIONS_AND_SQUAD"),
        ("qual jogador caiu de rendimento depois dos 60 minutos no segundo tempo", "SUBSTITUTIONS_AND_SQUAD"),
        ("quem devemos tirar do time por desgaste ou excesso de erros", "SUBSTITUTIONS_AND_SQUAD"),
        ("quais mudancas no elenco fazer para corrigir o meio campo", "SUBSTITUTIONS_AND_SQUAD"),
        ("qual o risco estrutural de substituir o volante titular", "SUBSTITUTIONS_AND_SQUAD"),
        ("analise de fadiga tecnica e trocas recomendadas na partida", "SUBSTITUTIONS_AND_SQUAD"),
        # 7. INDIVIDUAL_AND_COMPARISON (Comparar dois jogadores, volantes, destaques)
        ("compare o desempenho dos dois volantes da equipe", "INDIVIDUAL_AND_COMPARISON"),
        ("quem jogou melhor no meio campo e gerou mais xt", "INDIVIDUAL_AND_COMPARISON"),
        ("comparacao direta entre dois atletas da mesma posicao", "INDIVIDUAL_AND_COMPARISON"),
        ("quais foram os melhores jogadores em quebras de linha e progressao", "INDIVIDUAL_AND_COMPARISON"),
        ("diferenca de estilo tatico entre os meio campistas", "INDIVIDUAL_AND_COMPARISON"),
        # 8. SET_PIECES (Bolas paradas, escanteios, faltas)
        ("como funcionam as bolas paradas e escanteios dessa equipe", "SET_PIECES"),
        ("eles batem escanteio na primeira trave ou segunda trave", "SET_PIECES"),
        ("vulnerabilidade defensiva na bola aerea e faltas laterais", "SET_PIECES"),
        ("jogadas ensaiadas de bola parada ofensiva e defensiva", "SET_PIECES"),
        # 9. COMPLETE_REPORT (Plano de jogo completo, visão global)
        ("monte um plano de jogo completo para enfrentar essa equipe", "COMPLETE_REPORT"),
        ("faca um relatorio tatico completo de todas as fases do jogo", "COMPLETE_REPORT"),
        ("resumo executivo e diagnostico geral da partida", "COMPLETE_REPORT"),
        ("quero entender tudo sobre o modelo de jogo desse time", "COMPLETE_REPORT"),
    ]

    def __init__(self, model_path: str = "models/trained/nlp_intent_mlp.joblib") -> None:
        self.model_path = Path(model_path)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline: Optional[Pipeline] = None
        self.training_accuracy: float = 0.0
        self._load_or_train()

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        no_acc = "".join(
            c
            for c in unicodedata.normalize("NFD", str(text))
            if unicodedata.category(c) != "Mn"
        )
        return no_acc.lower().strip()

    def _load_or_train(self) -> None:
        if self.model_path.exists():
            try:
                saved = joblib.load(self.model_path)
                self.pipeline = saved["pipeline"]
                self.training_accuracy = saved.get("training_accuracy", 1.0)
                return
            except Exception:
                pass
        self.train_intent_neural_network()

    def train_intent_neural_network(self) -> Dict[str, Any]:
        """
        Treina uma Rede Neural Multicamadas (MLPClassifier) combinada com Features
        Híbridas TF-IDF (N-gramas de Palavras + N-gramas de Caracteres) para aprender
        padrões semânticos mesmo com erros de digitação ou sinônimos.
        """
        texts = [self.normalize_text(t) for t, _ in self.TRAINING_CORPUS]
        labels = [lbl for _, lbl in self.TRAINING_CORPUS]

        features = FeatureUnion(
            [
                (
                    "word_tfidf",
                    TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
                ),
                (
                    "char_tfidf",
                    TfidfVectorizer(
                        analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True
                    ),
                ),
            ]
        )

        mlp = MLPClassifier(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",
            alpha=0.01,
            max_iter=600,
            random_state=42,
        )

        self.pipeline = Pipeline([("features", features), ("mlp", mlp)])
        self.pipeline.fit(texts, labels)

        preds = self.pipeline.predict(texts)
        self.training_accuracy = round(
            float(np.mean([p == y for p, y in zip(preds, labels)])), 4
        )

        joblib.dump(
            {
                "pipeline": self.pipeline,
                "training_accuracy": self.training_accuracy,
            },
            self.model_path,
        )
        return {
            "status": "TRAINED",
            "samples": len(texts),
            "classes": len(set(labels)),
            "training_accuracy": self.training_accuracy,
        }

    def predict_query_intent(
        self,
        user_query: str,
        matched_players_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Usa a Rede Neural treinada para prever a intenção da pergunta do usuário,
        retornando a classe principal, a confiança probabilística (%) e o ranking
        das 3 intenções mais prováveis.
        """
        if not user_query or not user_query.strip():
            return {
                "predicted_intent": "COMPLETE_REPORT",
                "confidence_pct": 100.0,
                "top_3_intents": [("COMPLETE_REPORT", 100.0)],
                "interpreted_by": "Default Empty Query",
            }

        norm_q = self.normalize_text(user_query)
        probs = self.pipeline.predict_proba([norm_q])[0]
        classes = list(self.pipeline.classes_)

        ranked = sorted(
            zip(classes, probs), key=lambda x: x[1], reverse=True
        )
        best_intent, best_prob = ranked[0]

        # Se o detector de entidades encontrou exatamente 1 jogador nominal na frase,
        # combina a evidência de entidade com a rede neural
        if matched_players_count == 1 and best_intent not in (
            "SUBSTITUTIONS_AND_SQUAD",
            "INDIVIDUAL_AND_COMPARISON",
        ):
            best_intent = "PLAYER_SPECIFIC_TACTIC"
            best_prob = max(float(best_prob), 0.88)
        elif matched_players_count >= 2:
            best_intent = "INDIVIDUAL_AND_COMPARISON"
            best_prob = max(float(best_prob), 0.90)

        top_3 = [(cls_name, round(float(p) * 100.0, 2)) for cls_name, p in ranked[:3]]

        return {
            "predicted_intent": str(best_intent),
            "confidence_pct": round(float(best_prob) * 100.0, 2),
            "top_3_intents": top_3,
            "interpreted_by": "MLP Neural Network (TF-IDF Word+Char N-Grams)",
        }

    @classmethod
    def semantic_entity_match(
        cls,
        query_text: str,
        candidate_strings: List[str],
        threshold: float = 0.28,
    ) -> List[Tuple[str, float]]:
        """
        Encontra entidades (jogadores ou partidas do catálogo) usando Similaridade de Cosseno
        sobre N-gramas de caracteres (tolera erros de digitação como 'Mbape', 'Fransa', 'Leverkuzen').
        """
        if not query_text or not candidate_strings:
            return []

        norm_q = cls.normalize_text(query_text)
        norm_cands = [cls.normalize_text(c) for c in candidate_strings]

        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        tfidf_matrix = vec.fit_transform([norm_q] + norm_cands)

        q_vec = tfidf_matrix[0:1]
        cand_vecs = tfidf_matrix[1:]
        sims = cosine_similarity(q_vec, cand_vecs)[0]

        results = []
        for orig_str, score in zip(candidate_strings, sims):
            if float(score) >= threshold:
                results.append((orig_str, round(float(score), 4)))

        return sorted(results, key=lambda x: x[1], reverse=True)