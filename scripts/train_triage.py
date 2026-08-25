"""LoRA SFT of Sarvam-1 on distilled triage data (MPS/CPU friendly).

Mirrors the proven soup-sarvam.yaml recipe: LoRA r16 a16, cosine, 1 epoch.
Run inside ~/sarvam-soup/.venv (torch+trl+peft installed).
"""
import json
import sys
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE = "sarvamai/sarvam-1"
DATA = Path.home() / "sarvam-soup/data"
OUT = Path.home() / "sarvam-soup/output/sarvam-1-triage"

def rows(p):
    return [json.loads(l) for l in open(p)]

train_ds = Dataset.from_list(rows(DATA / "triage_train.jsonl"))
val_ds = Dataset.from_list(rows(DATA / "triage_val.jsonl"))

tok = AutoTokenizer.from_pretrained(BASE)
tok.pad_token = tok.eos_token

# append EOS so generation knows where to stop
train_ds = train_ds.map(lambda x: {"text": x["text"] + tok.eos_token})
val_ds = val_ds.map(lambda x: {"text": x["text"] + tok.eos_token})

model = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=torch.float32, low_cpu_mem_usage=True)
model.config.use_cache = False

cfg = SFTConfig(
    output_dir=str(OUT),
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    num_train_epochs=2,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_strategy="epoch",
    eval_strategy="steps",
    eval_steps=100,
    max_length=512,
    packing=False,
    seed=42,
    report_to=[],
)

peft_cfg = LoraConfig(
    r=16, lora_alpha=16, lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    task_type="CAUSAL_LM",
)

trainer = SFTTrainer(
    model=model,
    args=cfg,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    processing_class=tok,
    peft_config=peft_cfg,
)
trainer.train()
trainer.save_model(str(OUT))
tok.save_pretrained(str(OUT))
print("DONE ->", OUT)
