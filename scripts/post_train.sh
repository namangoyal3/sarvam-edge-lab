#!/usr/bin/env bash
# Post-training pipeline: merge LoRA -> GGUF f16 -> imatrix quantize (IQ3_XXS + Q4_K_M)
# Usage: bash scripts/post_train.sh [checkpoint_dir_name]   (default: checkpoint-<half steps>)
set -e
SOUP="$HOME/sarvam-soup"
CKPT="${1:-}"
cd "$SOUP"
[ -d "output/sarvam-1-triage/$CKPT" ] || CKPT=$(ls -d output/sarvam-1-triage/checkpoint-* | sort -V | tail -1 | xargs basename)
echo "merging from $CKPT ..."
.venv/bin/python - <<EOF
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base = AutoModelForCausalLM.from_pretrained("sarvamai/sarvam-1", torch_dtype=torch.float32)
m = PeftModel.from_pretrained(base, "output/sarvam-1-triage/$CKPT")
merged = m.merge_and_unload()
merged.save_pretrained("merged-triage")
AutoTokenizer.from_pretrained("sarvamai/sarvam-1").save_pretrained("merged-triage")
print("MERGE DONE")
EOF
.venv/bin/python llama.cpp/convert_hf_to_gguf.py merged-triage --outfile triage-v2-f16.gguf --outtype f16 2>&1 | tail -1
./llama.cpp/build/bin/llama-quantize --imatrix triage.imatrix triage-v2-f16.gguf sarvam-1-triage-v2-iq3xxs.gguf IQ3_XXS 2>&1 | tail -1
./llama.cpp/build/bin/llama-quantize --imatrix triage.imatrix triage-v2-f16.gguf sarvam-1-triage-v2-q4km.gguf Q4_K_M 2>&1 | tail -1
ls -lh sarvam-1-triage-v2-*.gguf | awk '{print $5, $9}'
echo "POST_TRAIN DONE"
