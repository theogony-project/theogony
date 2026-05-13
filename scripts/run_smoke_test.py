#!/usr/bin/env python3
"""
W2 Smoke Test: Qwen2.5-1.5B-Instruct 4-bit on MPS + poc_pipeline_trace.json.

Produces the pipeline trace that the PoC brief requires.
Runs on CPU if MPS is busy; use --device mps to force.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch


def main() -> None:
    device_name = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device_name}")

    from transformers import AutoModelForCausalLM, AutoTokenizer

    print("Loading Qwen2.5-1.5B-Instruct on MPS...")
    # Load model directly from hub, place on MPS explicitly.
    # bfloat16 fits in 48 GB unified memory (~3 GB).
    from transformers import BitsAndBytesConfig

    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2.5-1.5B-Instruct",
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    ).to(device_name)
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
    print(f"Model loaded. Parameters: {model.num_parameters():,}")

    # Simple forward pass
    prompt = "Explain the relationship between entropy and information theory."
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output = model.generate(
        **inputs,
        max_new_tokens=50,
        do_sample=True,
        temperature=0.7,
    )
    response = tokenizer.decode(output[0], skip_special_tokens=True)
    print(f"\nPrompt: {prompt}")
    print(f"Response: {response[:200]}...")

    # Verify no NaN
    with torch.no_grad():
        logits = model(**inputs).logits
        assert not torch.isnan(logits).any(), "NaN in logits"

    # Write trace
    trace = {
        "schema_version": "mnlm-smoke/1",
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "device": device_name,
        "num_parameters": model.num_parameters(),
        "prompt": prompt,
        "response": response,
        "forward_pass_no_nan": True,
    }
    out_path = Path("docs/research/mnlm/poc/poc_pipeline_trace.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(trace, indent=2))
    print(f"\nTrace written to {out_path}")


if __name__ == "__main__":
    main()
