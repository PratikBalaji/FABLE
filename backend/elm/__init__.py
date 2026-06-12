"""
ELM (Embedded Language Model) — dynamic role declaration for the adversarial pipeline.

Runs a local ONNX model (Phi-3-mini) to generate task-aware system prompts,
model assignments, token budgets, and activation decisions for each adversarial
agent role. Falls back to static declarations when the ELM is disabled or unavailable.
"""
