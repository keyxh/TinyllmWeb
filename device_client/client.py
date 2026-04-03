import sys
import os
import asyncio
import argparse
import json
import time
import subprocess
import psutil
import signal
import GPUtil
import re
from typing import Optional, Dict, Any
import httpx
import websockets
import socket
import uuid

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

DEVICE_CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DEVICE_CLIENT_DIR))


DEVICE_CONFIG_FILE = os.path.join(DEVICE_CLIENT_DIR, "device_config.json")


def generate_device_name() -> str:
    try:
        hostname = socket.gethostname()
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0, 8*6, 8)][::-1])
        return f"{hostname}-{mac[:8]}"
    except:
        return f"device-{uuid.uuid4().hex[:8]}"


def load_device_config() -> dict:
    try:
        if os.path.exists(DEVICE_CONFIG_FILE):
            with open(DEVICE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}


def save_device_config(config: dict):
    try:
        with open(DEVICE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Device] 保存配置失败: {e}")


class DeviceClient:
    def __init__(self, server_url: str, device_name: str, port: int, model_source: str = "modelsource", mode: str = "normal", frp_server: str = None, frp_token: str = None):
        self.server_url = server_url.rstrip('/')
        self.device_name = device_name
        self.port = port
        self.model_source = model_source
        self.mode = mode
        self.frp_server = frp_server
        self.frp_token = frp_token
        self.device_key: Optional[str] = None
        self.device_id: Optional[int] = None
        self.ws_connected = False
        self.running_tasks: Dict[int, subprocess.Popen] = {}
        self.running_deployments: Dict[int, subprocess.Popen] = {}
        self.api_servers: Dict[int, int] = {}
        self.frp_processes: Dict[int, subprocess.Popen] = {}
        self.frp_status: Dict[int, dict] = {}
        
        self.load_config()
    
    def load_config(self):
        config = load_device_config()
        if config:
            self.device_key = config.get("device_key")
            self.device_id = config.get("device_id")
            if self.device_key and self.device_id:
                print(f"[Device] 从本地加载设备信息: ID={self.device_id}")
    
    def save_config(self):
        if self.device_key and self.device_id:
            config = {
                "device_key": self.device_key,
                "device_id": self.device_id,
                "device_name": self.device_name,
                "server_url": self.server_url
            }
            save_device_config(config)
            print(f"[Device] 设备信息已保存到本地")
        
    def get_gpu_info(self) -> tuple[str, int]:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                gpu_info = f"{gpu.name} ({gpu.memoryTotal}MB)"
                vram_total = int(gpu.memoryTotal)
                return gpu_info, vram_total
        except:
            pass
        
        return "Unknown GPU", 8192
    
    def get_vram_usage(self) -> tuple[int, int]:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                vram_used = int(gpu.memoryUsed)
                vram_free = int(gpu.memoryFree)
                return vram_used, vram_free
        except:
            pass
        
        return 0, 8192
    
    async def register(self) -> bool:
        if self.device_key and self.device_id:
            print(f"[Device] 设备已注册，使用本地保存的密钥")
            await self.update_device_info()
            return True
        
        gpu_info, vram_total = self.get_gpu_info()
        
        data = {
            "device_name": self.device_name,
            "ip": "127.0.0.1",
            "port": self.port,
            "gpu_info": gpu_info,
            "vram_total": vram_total,
            "mode": self.mode,
            "frp_server": self.frp_server if self.mode == "frp" else None
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.server_url}/api/device/register",
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success"):
                    self.device_key = result["data"]["device_key"]
                    self.device_id = result["data"]["device_id"]
                    self.save_config()
                    print(f"[Device] 注册成功，设备ID: {self.device_id}")
                    return True
                else:
                    print(f"[Device] 注册失败: {result.get('message')}")
                    return False
        except Exception as e:
            print(f"[Device] 注册失败: {e}")
            return False
    
    async def update_device_info(self):
        gpu_info, vram_total = self.get_gpu_info()
        
        data = {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "ip": "127.0.0.1",
            "port": self.port,
            "gpu_info": gpu_info,
            "vram_total": vram_total,
            "mode": self.mode,
            "frp_server": self.frp_server if self.mode == "frp" else None
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.server_url}/api/device/update",
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success"):
                    print(f"[Device] 设备信息更新成功")
                else:
                    print(f"[Device] 设备信息更新失败: {result.get('message')}")
        except Exception as e:
            print(f"[Device] 设备信息更新失败: {e}")
    
    async def send_log(self, log_type: str, level: str, message: str, task_id: int = None, deployment_id: int = None):
        if not self.device_key:
            return
        
        data = {
            "device_key": self.device_key,
            "log_type": log_type,
            "level": level,
            "message": message,
            "task_id": task_id,
            "deployment_id": deployment_id
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/logs",
                    json=data
                )
        except Exception as e:
            print(f"[Device] 发送日志失败: {e}")
    
    async def send_heartbeat(self):
        if not self.device_key:
            return
        
        vram_used, vram_free = self.get_vram_usage()
        
        data = {
            "device_key": self.device_key,
            "vram_used": vram_used,
            "vram_free": vram_free
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.server_url}/api/device/heartbeat",
                    json=data
                )
                response.raise_for_status()
        except Exception as e:
            print(f"[Device] 心跳失败: {e}")
    
    async def get_pending_tasks(self) -> list:
        if not self.device_key:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.get(
                    f"{self.server_url}/api/device/tasks/pending",
                    params={"device_key": self.device_key}
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success"):
                    return result.get("data", [])
        except Exception as e:
            print(f"[Device] 获取任务失败: {e}")
        
        return []
    
    async def accept_task(self, task_id: int) -> bool:
        if not self.device_key:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.post(
                    f"{self.server_url}/api/device/tasks/accept",
                    params={"device_key": self.device_key, "task_id": task_id}
                )
                response.raise_for_status()
                result = response.json()
                return result.get("success", False)
        except Exception as e:
            print(f"[Device] 接受任务失败: {e}")
            return False
    
    async def update_task_progress(self, task_id: int, progress: float, logs: str = ""):
        if not self.device_key:
            return
        
        data = {
            "device_key": self.device_key,
            "task_id": task_id,
            "progress": progress,
            "log": logs
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/tasks/progress",
                    json=data
                )
        except Exception as e:
            print(f"[Device] 更新进度失败: {e}")
    
    async def complete_task(self, task_id: int, lora_path: str):
        if not self.device_key:
            return
        
        data = {
            "device_key": self.device_key,
            "task_id": task_id,
            "lora_path": lora_path
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/tasks/complete",
                    json=data
                )
        except Exception as e:
            print(f"[Device] 完成任务失败: {e}")
    
    async def fail_task(self, task_id: int, error_message: str):
        if not self.device_key:
            return
        
        data = {
            "device_key": self.device_key,
            "task_id": task_id,
            "error_message": error_message
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/tasks/failed",
                    json=data
                )
        except Exception as e:
            print(f"[Device] 标记失败失败: {e}")
    
    async def get_deployments(self) -> list:
        if not self.device_key:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.get(
                    f"{self.server_url}/api/device/deployments",
                    params={"device_key": self.device_key}
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success"):
                    data = result.get("data", [])
                    print(f"[Debug] API返回部署数据: {len(data)} 个")
                    if data:
                        for d in data:
                            print(f"[Debug] 部署: id={d.get('deployment_id')}, device_id={d.get('device_id')}, model={d.get('model_name')}")
                    return data
        except Exception as e:
            print(f"[Device] 获取部署失败: {e}")
        
        return []
    
    async def run_training(self, task_data: Dict[str, Any]) -> bool:
        task_id = task_data["task_id"]
        model_name = task_data["model_name"]
        base_model = task_data["base_model"]
        dataset_filename = task_data.get("dataset_filename", "dataset.jsonl")
        dataset_content_b64 = task_data.get("dataset_content", "")
        training_params = json.loads(task_data.get("training_params", "{}"))
        
        await self.send_log("training", "INFO", f"开始训练任务 {task_id}，模型: {model_name}", task_id=task_id)
        
        datasets_dir = os.path.join(DEVICE_CLIENT_DIR, "datasets")
        os.makedirs(datasets_dir, exist_ok=True)
        
        local_dataset_path = os.path.join(datasets_dir, f"{task_id}_{dataset_filename}")
        
        try:
            if dataset_content_b64:
                import base64
                print(f"[Training] 正在保存数据集: {dataset_filename}")
                await self.send_log("training", "INFO", f"正在保存数据集: {dataset_filename}", task_id=task_id)
                with open(local_dataset_path, 'wb') as f:
                    f.write(base64.b64decode(dataset_content_b64))
                print(f"[Training] 数据集已保存: {local_dataset_path}")
                await self.send_log("training", "INFO", f"数据集已保存: {local_dataset_path}", task_id=task_id)
            else:
                print(f"[Training] 警告: 未找到数据集内容")
                await self.send_log("training", "ERROR", "未找到数据集内容", task_id=task_id)
                await self.fail_task(task_id, "数据集内容不存在")
                return False
        except Exception as e:
            print(f"[Training] 数据集保存失败: {e}")
            await self.send_log("training", "ERROR", f"数据集保存失败: {str(e)}", task_id=task_id)
            await self.fail_task(task_id, f"数据集保存失败: {str(e)}")
            return False
        
        output_dir = f"./trained_models/{task_id}_{model_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        script_path = os.path.join(os.path.dirname(__file__), "fine_tune.py")
        cmd = [
            sys.executable, script_path,
            "--model_name", base_model,
            "--model_source", self.model_source,
            "--data_file", local_dataset_path,
            "--output_dir", output_dir,
            "--num_epochs", str(training_params.get("num_epochs", 20)),
            "--batch_size", str(training_params.get("batch_size", 2)),
            "--learning_rate", str(training_params.get("learning_rate", 5e-4)),
            "--lora_r", str(training_params.get("lora_r", 128)),
            "--lora_alpha", str(training_params.get("lora_alpha", 32)),
            "--max_length", str(training_params.get("max_length", 512))
        ]
        
        await self.send_log("training", "INFO", f"训练参数: {training_params}", task_id=task_id)
        
        try:
            print(f"[Training] 开始训练任务 {task_id}")
            await self.send_log("training", "INFO", f"启动训练进程，命令: {' '.join(cmd)}", task_id=task_id)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.running_tasks[task_id] = process
            
            last_progress_update = 0
            progress = 0.0
            
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    line = line.strip()
                    print(f"[Training] {line}")
                    
                    current_time = time.time()
                    
                    if "Progress:" in line or "Step" in line or "Epoch" in line:
                        try:
                            if "Progress:" in line:
                                progress_str = line.split("Progress:")[1].split("%")[0].strip()
                                progress = float(progress_str) / 100
                            elif "Step" in line:
                                match = re.search(r'Step (\d+)/(\d+)', line)
                                if match:
                                    step = int(match.group(1))
                                    total = int(match.group(2))
                                    progress = min(0.95, step / total) if total > 0 else 0
                                else:
                                    progress = 0
                            else:
                                progress = 0
                        except:
                            progress = 0
                    
                    if current_time - last_progress_update >= 5:
                        await self.update_task_progress(task_id, progress, line)
                        await self.send_log("training", "INFO", line, task_id=task_id)
                        last_progress_update = current_time
            
            return_code = process.poll()
            
            if return_code == 0:
                print(f"[Training] 训练任务 {task_id} 完成")
                await self.send_log("training", "INFO", "训练完成", task_id=task_id)
                await self.update_task_progress(task_id, 1.0, "训练完成")
                await self.complete_task(task_id, output_dir)
                return True
            else:
                error_output = process.stdout.read()
                print(f"[Training] 训练任务 {task_id} 失败: {error_output}")
                await self.send_log("training", "ERROR", f"训练失败: {error_output[:500]}", task_id=task_id)
                await self.fail_task(task_id, f"训练失败: {error_output[:500]}")
                return False
                
        except Exception as e:
            print(f"[Training] 训练任务 {task_id} 异常: {e}")
            await self.send_log("training", "ERROR", f"训练异常: {str(e)}", task_id=task_id)
            await self.fail_task(task_id, str(e))
            return False
        finally:
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if os.path.exists(local_dataset_path):
                try:
                    os.remove(local_dataset_path)
                    print(f"[Training] 已清理数据集文件: {local_dataset_path}")
                    await self.send_log("training", "INFO", f"已清理数据集文件: {local_dataset_path}", task_id=task_id)
                except:
                    pass
    
    async def start_api_server(self, deployment_data: Dict[str, Any]) -> bool:
        deployment_id = deployment_data["deployment_id"]
        model_name = deployment_data["model_name"]
        base_model = deployment_data["base_model"]
        lora_path = deployment_data["lora_path"]
        port = deployment_data["port"]
        
        print(f"[API] === 开始部署 ===")
        print(f"[API] 部署ID: {deployment_id}")
        print(f"[API] 模型: {model_name}")
        print(f"[API] 基础模型: {base_model}")
        print(f"[API] LoRA路径: {lora_path}")
        print(f"[API] 端口: {port}")
        print(f"[API] 模式: {self.mode}")
        
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        api_server_path = os.path.join(os.path.dirname(__file__), "apiServer.py")
        
        cmd = [
            sys.executable,
            api_server_path,
            "--port", str(port),
            "--lora_path", lora_path,
            "--base_model", base_model
        ]
        
        try:
            print(f"[API] 启动命令: {' '.join(cmd)}")
            
            log_file = os.path.join(logs_dir, f"api_{deployment_id}.log")
            with open(log_file, 'w', encoding='utf-8') as log_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            
            self.running_deployments[deployment_id] = process
            self.api_servers[deployment_id] = port
            
            print(f"[API] API服务器启动成功，PID: {process.pid}")
            print(f"[API] 日志文件: {log_file}")
            
            await asyncio.sleep(2)
            
            if process.poll() is not None:
                error_msg = f"API服务器启动后立即退出，退出码: {process.returncode}"
                print(f"[API] {error_msg}")
                if deployment_id in self.running_deployments:
                    del self.running_deployments[deployment_id]
                if deployment_id in self.api_servers:
                    del self.api_servers[deployment_id]
                await self.notify_deployment_failed(deployment_id, error_msg)
                return False
            
            vram_used, vram_free = self.get_vram_usage()
            
            print(f"[API] 当前运行模式: mode={self.mode}, frp_server={self.frp_server}")
            
            if self.mode == "frp":
                frp_remote_addr = await self.start_and_wait_frpc(deployment_id, port)
                if not frp_remote_addr:
                    error_msg = "FRP内网穿透启动失败或连接超时"
                    print(f"[API] {error_msg}")
                    self.stop_api_server(deployment_id)
                    await self.notify_deployment_failed(deployment_id, error_msg)
                    return False
                
                await self.notify_deployment_started(deployment_id, vram_used, frp_remote_addr)
            else:
                print(f"[API] 普通模式，直接使用本地地址")
                await self.notify_deployment_started(deployment_id, vram_used, None)
            
            return True
            
        except Exception as e:
            error_msg = f"启动异常: {str(e)}"
            print(f"[API] {error_msg}")
            import traceback
            traceback.print_exc()
            await self.notify_deployment_failed(deployment_id, error_msg)
            return False
    
    async def start_and_wait_frpc(self, deployment_id: int, local_port: int, timeout: int = 10):
        if not self.frp_server:
            print(f"[FRP] FRP模式需要配置frp_server")
            return None
        
        frp_port = 32000 + deployment_id
        frpc_dir = os.path.dirname(__file__)
        
        frpc_toml = f"""serverAddr = "{self.frp_server.split(':')[0]}"
serverPort = {self.frp_server.split(':')[1]}

[[proxies]]
name = "deployment_{deployment_id}"
type = "tcp"
localIP = "127.0.0.1"
localPort = {local_port}
remotePort = {frp_port}
"""
        
        frpc_config_path = os.path.join(frpc_dir, f"frpc_{deployment_id}.toml")
        with open(frpc_config_path, 'w', encoding='utf-8') as f:
            f.write(frpc_toml)
        
        print(f"[FRP] FRP配置文件已生成: {frpc_config_path}")
        print(f"[FRP] FRP服务器: {self.frp_server}")
        print(f"[FRP] 本地端口: {local_port}")
        print(f"[FRP] 远程端口: {frp_port}")
        
        try:
            if os.name == 'nt':
                frpc_exe = os.path.join(frpc_dir, "frpc.exe")
            else:
                frpc_exe = os.path.join(frpc_dir, "frpc")
            
            if not os.path.exists(frpc_exe):
                print(f"[FRP] 警告: frpc可执行文件不存在: {frpc_exe}")
                print(f"[FRP] 请手动下载frpc并放置在: {frpc_dir}")
                return None
            
            logs_dir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(logs_dir, exist_ok=True)
            log_file = os.path.join(logs_dir, f"frpc_{deployment_id}.log")
            with open(log_file, 'w', encoding='utf-8') as log_f:
                process = subprocess.Popen(
                    [frpc_exe, "-c", frpc_config_path],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True
                )
            self.frp_processes[deployment_id] = process
            
            print(f"[FRP] FRP客户端启动成功，PID: {process.pid}")
            print(f"[FRP] 日志文件: {log_file}")
            
            self.frp_status[deployment_id] = {"connected": False, "remote_addr": None}
            
            for i in range(timeout):
                await asyncio.sleep(1)
                
                if process.poll() is not None:
                    print(f"[FRP] FRP进程启动后退出，退出码: {process.returncode}")
                    with open(log_file, 'r', encoding='utf-8') as lf:
                        log_content = lf.read()[-500:]
                        print(f"[FRP] 日志内容: {log_content}")
                    return None
                
                with open(log_file, 'r', encoding='utf-8') as lf:
                    log_content = lf.read()
                    if "start proxy success" in log_content or "started" in log_content.lower():
                        remote_addr = f"{self.frp_server.split(':')[0]}:{frp_port}"
                        self.frp_status[deployment_id] = {"connected": True, "remote_addr": remote_addr}
                        print(f"[FRP] FRP连接成功，远程地址: {remote_addr}")
                        return remote_addr
            
            print(f"[FRP] FRP连接超时，等待了 {timeout} 秒")
            return None
            
        except Exception as e:
            print(f"[FRP] FRP启动失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def notify_deployment_started(self, deployment_id: int, vram_used: int, frp_remote_addr: str = None):
        try:
            if frp_remote_addr:
                api_url = f"http://{frp_remote_addr}/v1"
            else:
                api_url = f"http://127.0.0.1:{self.api_servers.get(deployment_id, 8000)}/v1"
            
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/deployments/started",
                    json={
                        "device_key": self.device_key,
                        "deployment_id": deployment_id,
                        "vram_used": vram_used,
                        "api_url": api_url
                    }
                )
                print(f"[Device] 已通知后端部署 {deployment_id} 启动成功，API: {api_url}")
        except Exception as e:
            print(f"[Device] 通知后端部署启动失败: {e}")
    
    async def notify_deployment_crashed(self, deployment_id: int, error_message: str):
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/deployments/crashed",
                    json={
                        "device_key": self.device_key,
                        "deployment_id": deployment_id,
                        "error_message": error_message
                    }
                )
                print(f"[Device] 已通知后端部署 {deployment_id} 崩溃")
        except Exception as e:
            print(f"[Device] 通知后端部署崩溃失败: {e}")
    
    async def notify_deployment_failed(self, deployment_id: int, error_message: str):
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                await client.post(
                    f"{self.server_url}/api/device/deployments/failed",
                    json={
                        "device_key": self.device_key,
                        "deployment_id": deployment_id,
                        "error_message": error_message
                    }
                )
                print(f"[Device] 已通知后端部署 {deployment_id} 启动失败: {error_message}")
        except Exception as e:
            print(f"[Device] 通知后端部署失败失败: {e}")
    
    async def check_deployments_health(self):
        crashed_deployments = []
        for deployment_id, process in list(self.running_deployments.items()):
            if process is not None and process.poll() is not None:
                print(f"[Health] 部署 {deployment_id} 进程已退出，退出码: {process.returncode}")
                crashed_deployments.append((deployment_id, f"进程退出，退出码: {process.returncode}"))
        
        for deployment_id, error_output in crashed_deployments:
            await self.notify_deployment_crashed(deployment_id, error_output)
            self.stop_api_server(deployment_id)
    
    def stop_api_server(self, deployment_id: int):
        if deployment_id in self.running_deployments:
            process = self.running_deployments[deployment_id]
            if process is None:
                print(f"[Device] 部署 {deployment_id} 的进程已为 None，直接清理")
                del self.running_deployments[deployment_id]
                if deployment_id in self.api_servers:
                    del self.api_servers[deployment_id]
                return
            
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            
            if deployment_id in self.running_deployments:
                del self.running_deployments[deployment_id]
            if deployment_id in self.api_servers:
                del self.api_servers[deployment_id]
            
            log_file = os.path.join(DEVICE_CLIENT_DIR, f"api_log_{deployment_id}.txt")
            if os.path.exists(log_file):
                try:
                    os.remove(log_file)
                except Exception as e:
                    print(f"[API] 删除日志文件失败: {e}")
            
            print(f"[API] API服务器 {deployment_id} 已停止")
        else:
            print(f"[Device] 部署 {deployment_id} 不在运行列表中")
        
        if deployment_id in self.frp_processes:
            frp_process = self.frp_processes[deployment_id]
            frp_process.terminate()
            try:
                frp_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                frp_process.kill()
            
            del self.frp_processes[deployment_id]
            
            frpc_config_path = os.path.join(DEVICE_CLIENT_DIR, f"frpc_{deployment_id}.toml")
            if os.path.exists(frpc_config_path):
                try:
                    os.remove(frpc_config_path)
                except Exception as e:
                    print(f"[FRP] 删除配置文件失败: {e}")
            
            print(f"[FRP] FRP进程 {deployment_id} 已停止")
    
    async def websocket_handler(self):
        reconnect_count = 0
        max_reconnect_wait = 60
        
        while True:
            try:
                if not self.device_key:
                    print("[WebSocket] 等待设备密钥...")
                    await asyncio.sleep(5)
                    continue
                    
                ws_url = f"{self.server_url.replace('http', 'ws')}/api/device/ws/{self.device_key}"
                print(f"[WebSocket] 尝试连接...")
                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=60) as websocket:
                    print("[WebSocket] 连接成功")
                    reconnect_count = 0
                    self.ws_connected = True
                    
                    while True:
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                            data = json.loads(message)
                            
                            if data.get("type") == "command":
                                await self.handle_command(data)
                            elif data.get("type") == "ping":
                                await websocket.send(json.dumps({"type": "pong"}))
                                
                        except asyncio.TimeoutError:
                            try:
                                await websocket.ping()
                            except Exception as e:
                                print(f"[WebSocket] 心跳失败: {e}")
                                self.ws_connected = False
                                break
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"[WebSocket] 连接关闭: {e}")
                            self.ws_connected = False
                            break
                        except Exception as e:
                            print(f"[WebSocket] 接收消息错误: {e}")
                            self.ws_connected = False
                            break
                            
            except websockets.exceptions.ConnectionClosed as e:
                self.ws_connected = False
                print(f"[WebSocket] 连接关闭: {e}")
            except Exception as e:
                self.ws_connected = False
                reconnect_count += 1
                wait_time = min(max_reconnect_wait, 5 * (2 ** min(reconnect_count, 5)))
                print(f"[WebSocket] 连接断开: {e}，{wait_time}秒后重连 ({reconnect_count}次)")
                await asyncio.sleep(wait_time)
    
    async def handle_command(self, data: Dict[str, Any]):
        command = data.get("command")
        print(f"[Command] 收到命令: {command}")
        
        if command == "start_training":
            task_data = data.get("task_data")
            print(f"[Command] 开始训练任务: {task_data.get('task_id')}")
            asyncio.create_task(self.run_training(task_data))
        elif command == "stop_training":
            task_id = data.get("task_id")
            print(f"[Command] 停止训练任务: {task_id}")
            if task_id in self.running_tasks:
                self.running_tasks[task_id].terminate()
        elif command == "start_deployment":
            deployment_data = data.get("deployment_data")
            print(f"[Command] 开始部署: {deployment_data.get('deployment_id')}, 模型: {deployment_data.get('model_name')}")
            await self.start_api_server(deployment_data)
        elif command == "stop_deployment":
            deployment_id = data.get("deployment_id")
            print(f"[Command] 停止部署: {deployment_id}")
            self.stop_api_server(deployment_id)
    
    async def task_loop(self):
        while True:
            try:
                pending_tasks = await self.get_pending_tasks()
                
                for task in pending_tasks:
                    task_id = task["task_id"]
                    if task_id not in self.running_tasks:
                        accepted = await self.accept_task(task_id)
                        if accepted:
                            print(f"[TaskLoop] 开始训练任务: {task_id}")
                            asyncio.create_task(self.run_training(task))
                
                deployments = await self.get_deployments()
                print(f"[TaskLoop] 获取到 {len(deployments)} 个部署任务, device_id={self.device_id}")
                
                if deployments:
                    for d in deployments:
                        print(f"[TaskLoop] 部署详情: id={d.get('deployment_id')}, model={d.get('model_name')}, port={d.get('port')}")
                
                current_deployments = set(d["deployment_id"] for d in deployments)
                
                for deployment_id in list(self.running_deployments.keys()):
                    if deployment_id not in current_deployments:
                        print(f"[TaskLoop] 停止已取消的部署: {deployment_id}")
                        self.stop_api_server(deployment_id)
                
                for deployment in deployments:
                    deployment_id = deployment["deployment_id"]
                    port = deployment.get("port", 8000)
                    
                    if deployment_id in self.running_deployments:
                        process = self.running_deployments[deployment_id]
                        if process is None or process.poll() is None:
                            print(f"[TaskLoop] 部署 {deployment_id} 已在运行中，跳过启动")
                        else:
                            print(f"[TaskLoop] 部署 {deployment_id} 进程已退出，重新启动")
                            self.stop_api_server(deployment_id)
                            await self.start_api_server(deployment)
                    else:
                        is_port_in_use = await self.is_port_in_use(port)
                        if is_port_in_use:
                            print(f"[TaskLoop] 端口 {port} 已被占用，检查是否需要重新启动部署 {deployment_id}")
                            try:
                                import socket
                                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                sock.settimeout(2)
                                result = sock.connect_ex(('127.0.0.1', port))
                                sock.close()
                                if result != 0:
                                    print(f"[TaskLoop] 端口 {port} 无响应，重新启动部署 {deployment_id}")
                                    await self.start_api_server(deployment)
                                else:
                                    print(f"[TaskLoop] 端口 {port} 正在运行，通知后端部署已启动")
                                    self.running_deployments[deployment_id] = None
                                    self.api_servers[deployment_id] = port
                                    vram_used, _ = self.get_vram_usage()
                                    await self.notify_deployment_started(deployment_id, vram_used, None)
                            except Exception as e:
                                print(f"[TaskLoop] 检查端口失败: {e}")
                                await self.start_api_server(deployment)
                        else:
                            print(f"[TaskLoop] 启动部署: {deployment_id}, 模型: {deployment.get('model_name')}")
                            await self.start_api_server(deployment)
                
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"[TaskLoop] 错误: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(10)
    
    async def is_port_in_use(self, port: int) -> bool:
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    async def heartbeat_loop(self):
        while True:
            await self.send_heartbeat()
            vram_used, vram_free = self.get_vram_usage()
            print(f"[Heartbeat] 设备状态: device_id={self.device_id}, vram_used={vram_used}, vram_free={vram_free}")
            await self.check_deployments_health()
            await asyncio.sleep(30)
    
    async def run(self):
        print(f"[Device] 设备客户端启动")
        print(f"[Device] 服务器地址: {self.server_url}")
        print(f"[Device] 设备名称: {self.device_name}")
        
        if sys.platform != 'win32':
            def signal_handler():
                print("\n[Device] 收到退出信号，正在关闭...")
                for task_id, process in list(self.running_tasks.items()):
                    process.terminate()
                for deployment_id, process in list(self.running_deployments.items()):
                    process.terminate()
                sys.exit(0)
            
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
        
        if not await self.register():
            print("[Device] 注册失败，退出")
            return
        
        await asyncio.gather(
            self.heartbeat_loop(),
            self.task_loop(),
            self.websocket_handler()
        )


def main():
    parser = argparse.ArgumentParser(description="TinyLLM设备客户端")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:8000", help="服务器地址")
    parser.add_argument("--name", type=str, default=None, help="设备名称（不指定则自动生成）")
    parser.add_argument("--port", type=int, default=9000, help="设备端口")
    parser.add_argument("--model_source", type=str, default="modelscope", choices=["modelscope", "huggingface"], help="模型源：modelscope或huggingface（默认：modelscope）")
    parser.add_argument("--mode", type=str, default="normal", choices=["normal", "frp"], help="运行模式：normal（普通公网模式）或frp（FRP内网穿透模式，默认：normal）")
    parser.add_argument("--frp_server", type=str, default=None, help="FRP服务器地址（FRP模式必需，例如：38.150.4.149:7000）")
    
    args = parser.parse_args()
    
    device_name = args.name if args.name else generate_device_name()
    print(f"[Device] 自动生成的设备名称: {device_name}")
    print(f"[Device] 模型源: {args.model_source}")
    print(f"[Device] 运行模式: {args.mode}")
    if args.mode == "frp":
        print(f"[FRP] FRP服务器: {args.frp_server}")
    
    client = DeviceClient(args.server, device_name, args.port, args.model_source, args.mode, args.frp_server, None)
    asyncio.run(client.run())


if __name__ == "__main__":
    main()
