import sys
import os
import argparse
import json
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, AsyncGenerator
import asyncio

os.environ['TRANSFORMERS_NO_ADAPTER_WARNING'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

class FakeAudioUtils:
    AudioInput = None
    def load_audio(*args, **kwargs):
        raise ImportError("Audio not supported")

sys.modules['transformers.audio_utils'] = FakeAudioUtils

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    PEFT_AVAILABLE = True
except Exception as e:
    print(f"[ERROR] peft/transformers 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"[API] peft/transformers 导入成功")

app = FastAPI(title="TinyLLM API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None
tokenizer = None
device = None


class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="模型名称")
    messages: List[ChatMessage] = Field(..., description="对话消息列表")
    max_tokens: Optional[int] = Field(512, description="最大生成token数")
    temperature: Optional[float] = Field(0.7, description="生成温度")
    top_p: Optional[float] = Field(0.9, description="Top-p采样参数")
    top_k: Optional[int] = Field(50, description="Top-k采样参数")
    stream: Optional[bool] = Field(False, description="是否流式返回")
    stop: Optional[List[str]] = Field(None, description="停止词列表")


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[dict]
    usage: dict


class ChatCompletionStreamChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[dict]


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


def log(message: str):
    print(f"[API] {message}")
    sys.stdout.flush()


def load_model(lora_path: str, base_model: str = None):
    global model, tokenizer, device
    
    if not PEFT_AVAILABLE:
        error_msg = "peft 库加载失败，请检查依赖安装"
        log(f"ERROR: {error_msg}")
        raise ImportError(error_msg)
    
    log(f"LoRA路径: {lora_path}")
    
    adapter_config_path = os.path.join(lora_path, "adapter_config.json")
    
    if not base_model:
        if os.path.exists(adapter_config_path):
            with open(adapter_config_path, 'r', encoding='utf-8') as f:
                adapter_config = json.load(f)
            base_model = adapter_config.get("base_model_name_or_path")
            log(f"基础模型: {base_model}")
        else:
            error_msg = f"配置文件不存在: {adapter_config_path}"
            log(f"ERROR: {error_msg}")
            raise FileNotFoundError(error_msg)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"设备: {device}")
    
    try:
        log("加载分词器...")
        log(f"  正在从 {base_model} 下载分词器...")
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        log("  分词器加载完成")
    except Exception as e:
        log(f"ERROR: 分词器加载失败: {e}")
        raise
    
    try:
        log("加载基础模型...")
        log(f"  正在从 {base_model} 下载模型...")
        base_model_obj = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        log("  基础模型加载完成")
    except Exception as e:
        log(f"ERROR: 基础模型加载失败: {e}")
        raise
    
    try:
        log("加载LoRA...")
        model = PeftModel.from_pretrained(base_model_obj, lora_path)
        model = model.merge_and_unload()
        model.eval()
        log("  LoRA加载完成")
    except Exception as e:
        log(f"ERROR: LoRA加载失败: {e}")
        raise
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    log("模型加载完成")


def format_messages(messages: List[ChatMessage]) -> str:
    prompt = ""
    for msg in messages:
        if msg.role == "user":
            prompt += f"用户：{msg.content}\n"
        elif msg.role == "assistant":
            prompt += f"助手：{msg.content}\n"
        elif msg.role == "system":
            prompt += f"系统：{msg.content}\n"
    
    prompt += "助手："
    return prompt


async def generate_stream(
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    stop: Optional[List[str]] = None
) -> AsyncGenerator[str, None]:
    input_ids = tokenizer.encode(prompt, return_tensors="pt").to(device)
    
    generated_ids = input_ids.clone()
    completion_id = f"chatcmpl-{asyncio.get_event_loop().time()}"
    
    with torch.no_grad():
        for i in range(max_tokens):
            outputs = model(
                input_ids=generated_ids,
                use_cache=True
            )
            
            logits = outputs.logits[:, -1, :]
            
            if temperature > 0:
                logits = logits / temperature
            
            if top_k > 0:
                top_k_values, top_k_indices = torch.topk(logits, top_k)
                logits = torch.full_like(logits, float('-inf'))
                logits.scatter_(1, top_k_indices, top_k_values)
            
            if top_p < 1.0:
                sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                cumulative_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[:, 1:] = sorted_indices_to_remove[:, :-1].clone()
                sorted_indices_to_remove[:, 0] = 0
                indices_to_remove = sorted_indices_to_remove.scatter(1, sorted_indices, sorted_indices_to_remove)
                logits[indices_to_remove] = float('-inf')
            
            probs = torch.softmax(logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            
            generated_ids = torch.cat([generated_ids, next_token], dim=1)
            
            new_token = tokenizer.decode(next_token[0], skip_special_tokens=True)
            
            if stop:
                for stop_word in stop:
                    if stop_word in new_token:
                        yield new_token.split(stop_word)[0]
                        return
            
            yield new_token
            
            if tokenizer.eos_token_id in next_token[0]:
                break


def generate_completion(
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int,
    stop: Optional[List[str]] = None
) -> str:
    input_ids = tokenizer.encode(prompt, return_tensors="pt").to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            input_ids,
            max_new_tokens=max_tokens,
            temperature=temperature if temperature > 0 else 1.0,
            top_p=top_p,
            top_k=top_k,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.1
        )
    
    generated_text = tokenizer.decode(outputs[0][input_ids.shape[1]:], skip_special_tokens=True)
    
    if stop:
        for stop_word in stop:
            if stop_word in generated_text:
                generated_text = generated_text.split(stop_word)[0]
                break
    
    return generated_text


@app.get("/v1/models", response_model=ModelList)
async def list_models():
    return ModelList(
        object="list",
        data=[
            ModelInfo(
                id="tinyllm-model",
                created=int(asyncio.get_event_loop().time()),
                owned_by="user"
            )
        ]
    )


@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="模型未加载")
    
    prompt = format_messages(request.messages)
    
    if request.stream:
        async def stream_generator():
            completion_id = f"chatcmpl-{asyncio.get_event_loop().time()}"
            created = int(asyncio.get_event_loop().time())
            
            full_response = ""
            async for chunk in generate_stream(
                prompt,
                request.max_tokens,
                request.temperature,
                request.top_p,
                request.top_k,
                request.stop
            ):
                full_response += chunk
                
                chunk_data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None
                        }
                    ]
                }
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            
            final_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream"
        )
    else:
        generated_text = generate_completion(
            prompt,
            request.max_tokens,
            request.temperature,
            request.top_p,
            request.top_k,
            request.stop
        )
        
        completion_id = f"chatcmpl-{asyncio.get_event_loop().time()}"
        created = int(asyncio.get_event_loop().time())
        
        response = ChatCompletionResponse(
            id=completion_id,
            object="chat.completion",
            created=created,
            model=request.model,
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": generated_text
                    },
                    "finish_reason": "stop"
                }
            ],
            usage={
                "prompt_tokens": len(tokenizer.encode(prompt)),
                "completion_tokens": len(tokenizer.encode(generated_text)),
                "total_tokens": len(tokenizer.encode(prompt)) + len(tokenizer.encode(generated_text))
            }
        )
        
        return response


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "device": str(device) if device else "unknown"
    }


def main():
    parser = argparse.ArgumentParser(description="TinyLLM API服务器")
    parser.add_argument("--port", type=int, default=8000, help="服务端口")
    parser.add_argument("--lora_path", type=str, required=True, help="LoRA模型路径")
    parser.add_argument("--base_model", type=str, default=None, help="基础模型")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="服务地址")
    
    args = parser.parse_args()
    
    log(f"启动API服务器...")
    log(f"地址: {args.host}:{args.port}")
    log(f"LoRA路径: {args.lora_path}")
    if args.base_model:
        log(f"基础模型: {args.base_model}")
    
    try:
        load_model(args.lora_path, args.base_model)
        log("模型加载成功，开始服务...")
    except Exception as e:
        log(f"ERROR: 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
