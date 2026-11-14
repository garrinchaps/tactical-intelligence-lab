"""
NumericHallucinationGuard v2 — geração condicionada com validação numérica.

Pipeline: NumericExtractor → GroundTruthSet → Classifier (EXATO / DERIVADO / NÃO RASTREÁVEL)
→ Policy (bloqueia, regenera com contexto restrito, degrada de forma declarada) → Metrics.
"""
