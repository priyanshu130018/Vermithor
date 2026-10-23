import hashlib

files = {
    "prompt20_blind_keys": "evaluation/benchmarks/blind_generalization_fixtures/ground_truth/answer_keys.json",
    "prompt20_blind_manifest": "evaluation/benchmarks/blind_generalization_fixtures/manifest.json",
    "prompt21_held_out_keys": "evaluation/benchmarks/prompt21_held_out_fixtures/ground_truth/answer_keys.json",
    "prompt21_held_out_manifest": "evaluation/benchmarks/prompt21_held_out_fixtures/manifest.json",
    "global_manifest": "evaluation/results/evaluation_manifest.json",
}

for name, path in files.items():
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"{name}: {digest}")
