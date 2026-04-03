import sys
import os
import argparse
import json
import torch

os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HF_HUB_DISABLE_SYNC'] = '1'
os.environ['MODELSCOPE_CACHE'] = os.path.join(os.path.expanduser('~'), '.cache', 'modelscope')

class FakeAudioUtils:
    AudioInput = None
    def load_audio(*args, **kwargs):
        raise ImportError("Audio not supported")

sys.modules['transformers.audio_utils'] = FakeAudioUtils

from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import Dataset, DatasetDict
from typing import List, Dict

MODEL_SOURCE = 'modelscope'

class FineTuner:
    def __init__(self, model_name: str, data_file: str, output_dir: str, 
                 max_length: int = 512, num_epochs: int = 3, 
                 batch_size: int = 2, learning_rate: float = 2e-4,
                 lora_r: int = 64, lora_alpha: int = 16, lora_dropout: float = 0.1,
                 use_4bit: bool = False, progress_callback=None, log_callback=None):
        self.model_name = model_name
        self.data_file = data_file
        self.output_dir = output_dir
        self.max_length = max_length
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.lora_r = lora_r
        self.lora_alpha = lora_alpha
        self.lora_dropout = lora_dropout
        self.use_4bit = use_4bit
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        
        self.model = None
        self.tokenizer = None
        self.trainer = None
        
    def log(self, message: str):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[FineTune] {message}")
    
    def update_progress(self, progress: float, message: str = ""):
        if self.progress_callback:
            self.progress_callback(progress, message)
    
    def setup_model(self):
        self.log(f"正在加载模型: {self.model_name}")
        self.update_progress(0.1, "加载模型...")
        
        try:
            if MODEL_SOURCE == 'modelscope':
                from modelscope import snapshot_download
                model_dir = snapshot_download(self.model_name)
            else:
                model_dir = self.model_name
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_dir, 
                trust_remote_code=True
            )
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            model_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": torch.float16,
                "device_map": "auto"
            }
            
            if self.use_4bit:
                model_kwargs.update({
                    "load_in_4bit": True,
                    "bnb_4bit_compute_dtype": torch.float16,
                    "bnb_4bit_use_double_quant": True,
                    "bnb_4bit_quant_type": "nf4"
                })
            
            self.model = AutoModelForCausalLM.from_pretrained(
                model_dir,
                **model_kwargs
            )
            
            if self.use_4bit:
                self.model = prepare_model_for_kbit_training(self.model)
            
            target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
            
            lora_config = LoraConfig(
                r=self.lora_r,
                lora_alpha=self.lora_alpha,
                target_modules=target_modules,
                lora_dropout=self.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM"
            )
            
            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()
            
            self.update_progress(0.2, "模型加载完成")
            
        except Exception as e:
            self.log(f"模型加载失败: {str(e)}")
            raise
    
    def format_prompt(self, query: str, response: str = None) -> str:
        if response:
            return f"<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n{response}<|im_end|>"
        else:
            return f"<|im_start|>user\n{query}<|im_end|>\n<|im_start|>assistant\n"
    
    def load_data(self):
        self.log(f"正在加载数据: {self.data_file}")
        self.update_progress(0.25, "加载数据...")
        
        qa_pairs = []
        with open(self.data_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    query = item.get("query", "").strip()
                    response = item.get("response", "").strip()
                    
                    if query and response:
                        qa_pairs.append({
                            "query": query,
                            "response": response,
                            "text": self.format_prompt(query, response)
                        })
                except:
                    pass
        
        self.log(f"加载了 {len(qa_pairs)} 条数据")
        
        if qa_pairs:
            self.train_dataset = Dataset.from_list(qa_pairs)
        else:
            self.train_dataset = Dataset.from_list([])
        
        self.update_progress(0.3, "数据加载完成")
    
    def train(self):
        self.log("开始训练...")
        self.update_progress(0.4, "开始训练...")
        
        class CustomDataCollator:
            def __init__(self, tokenizer, max_length=512):
                self.tokenizer = tokenizer
                self.max_length = max_length
            
            def __call__(self, features):
                texts = [f["text"] for f in features]
                batch = self.tokenizer(
                    texts,
                    truncation=True,
                    padding=True,
                    max_length=self.max_length,
                    return_tensors="pt"
                )
                
                batch["labels"] = batch["input_ids"].clone()
                batch["labels"][batch["labels"] == self.tokenizer.pad_token_id] = -100
                
                return batch
        
        data_collator = CustomDataCollator(
            tokenizer=self.tokenizer,
            max_length=self.max_length
        )
        
        class ProgressCallback:
            def __init__(self, finetuner):
                self.finetuner = finetuner
            
            def on_init_end(self, args, state, control, **kwargs):
                pass
            
            def on_train_begin(self, args, state, control, **kwargs):
                self.finetuner.log("开始训练...")
                self.finetuner.update_progress(0.0, "开始训练")
            
            def on_train_end(self, args, state, control, **kwargs):
                self.finetuner.update_progress(1.0, "训练完成")
            
            def on_epoch_begin(self, args, state, control, **kwargs):
                pass
            
            def on_epoch_end(self, args, state, control, **kwargs):
                pass
            
            def on_step_begin(self, args, state, control, **kwargs):
                pass
            
            def on_step_end(self, args, state, control, **kwargs):
                if state.max_steps > 0:
                    progress = min(0.95, state.global_step / state.max_steps)
                    current_epoch = state.epoch if hasattr(state, 'epoch') else 0
                    self.finetuner.update_progress(
                        progress, 
                        f"Epoch {current_epoch+1}/{state.num_train_epochs}, Step {state.global_step}/{state.max_steps}"
                    )
            
            def on_substep_end(self, args, state, control, **kwargs):
                pass
            
            def on_pre_optimizer_step(self, args, state, control, **kwargs):
                pass
            
            def on_optimizer_step(self, args, state, control, **kwargs):
                pass
            
            def on_backward_end(self, args, state, control, **kwargs):
                pass
            
            def on_loss_compute(self, args, state, control, **kwargs):
                pass
            
            def on_log(self, args, state, control, logs=None, **kwargs):
                pass
            
            def on_save(self, args, state, control, **kwargs):
                pass
            
            def on_evaluate(self, args, state, control, **kwargs):
                pass
            
            def on_predict(self, control, metrics, args, state, **kwargs):
                pass
        
        training_args = TrainingArguments(
            output_dir=self.output_dir,
            num_train_epochs=self.num_epochs,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            learning_rate=self.learning_rate,
            fp16=True,
            logging_steps=10,
            save_steps=100,
            save_total_limit=1,
            load_best_model_at_end=False,
            report_to=None,
            dataloader_pin_memory=False,
            remove_unused_columns=False,
            max_grad_norm=1.0,
            lr_scheduler_type="cosine",
            gradient_checkpointing=False,
        )
        
        self.trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=self.train_dataset,
            data_collator=data_collator,
            processing_class=self.tokenizer,
            callbacks=[ProgressCallback(self)]
        )
        
        self.trainer.train()
        self.trainer.save_model()
        
        self.update_progress(1.0, "训练完成")
        self.log(f"模型已保存到: {self.output_dir}")

def main():
    global MODEL_SOURCE
    
    parser = argparse.ArgumentParser(description="TinyLLM微调工具")
    parser.add_argument("--model_name", type=str, required=True, help="模型名称")
    parser.add_argument("--model_source", type=str, default="modelscope", choices=["modelscope", "huggingface"], help="模型源")
    parser.add_argument("--data_file", type=str, required=True, help="训练数据文件")
    parser.add_argument("--output_dir", type=str, required=True, help="输出目录")
    parser.add_argument("--max_length", type=int, default=512, help="最大长度")
    parser.add_argument("--num_epochs", type=int, default=5, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=2, help="批次大小")
    parser.add_argument("--learning_rate", type=float, default=2e-4, help="学习率")
    parser.add_argument("--lora_r", type=int, default=64, help="LoRA rank")
    parser.add_argument("--lora_alpha", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--lora_dropout", type=float, default=0.1, help="LoRA dropout")
    parser.add_argument("--use_4bit", action='store_true', help="使用4bit量化")
    
    args = parser.parse_args()
    
    if args.model_source == 'modelscope':
        try:
            from modelscope import snapshot_download
            MODEL_SOURCE = 'modelscope'
        except ImportError:
            MODEL_SOURCE = 'huggingface'
    else:
        MODEL_SOURCE = 'huggingface'
    
    tuner = FineTuner(
        model_name=args.model_name,
        data_file=args.data_file,
        output_dir=args.output_dir,
        max_length=args.max_length,
        num_epochs=args.num_epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        use_4bit=args.use_4bit
    )
    
    tuner.setup_model()
    tuner.load_data()
    tuner.train()
    
    print("训练完成！")

if __name__ == "__main__":
    main()