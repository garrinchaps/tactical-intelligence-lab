"""
Testes Automatizados do Motor Neural de NLP (MLPClassifier + Cosine Similarity):
Comprova que a IA interpreta perguntas abertas não-literais e tolera erros de digitação.
"""

from src.intelligence.nlp_neural_router import TacticalNLPInterpreter
from src.reports.report_builder import QueryIntentRouter


def test_neural_nlp_understands_unseen_tactical_phrasing():
    """
    Verifica se a Rede Neural MLP classifica corretamente frases táticas coloquiais
    (sem depender de palavras-chave fixas) e retorna distribuição de probabilidades real.
    """
    nlp = TacticalNLPInterpreter()
    assert nlp.training_accuracy >= 0.95

    # Frase sem a palavra 'defesa' ou 'organização defensiva', mas pedindo para furar a retranca
    res_def = nlp.predict_query_intent("Como furar a retranca e achar buraco nas costas do lateral?")
    assert res_def["predicted_intent"] == "DEFENSIVE_VULNERABILITIES"
    assert res_def["confidence_pct"] > 30.0

    # Frase sobre pressão no tiro de meta
    res_press = nlp.predict_query_intent("Como subir a marcação no tiro de meta e travar o volante?")
    assert res_press["predicted_intent"] == "PRESSING_AND_BUILDUP"


def test_fuzzy_cosine_similarity_finds_misspelled_players():
    """
    Garante que mesmo que o usuário escreva 'anular o mbape' ou 'marcar o mesi' (com erro de grafia),
    o buscador vetorial por N-gramas de caracteres encontra o atleta real na partida.
    """
    roster = [
        "Lionel Andrés Messi Cuccittini",
        "Kylian Mbappé Lottin",
        "Rodrigo Javier De Paul",
    ]

    matched_mbappe = QueryIntentRouter.extract_target_players(
        "Monte uma tática para parar o mbape no corredor", roster
    )
    assert "Kylian Mbappé Lottin" in matched_mbappe