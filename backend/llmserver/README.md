# LlamaServer Setup

This directory contains the llama.cpp server binary and model files for local LLM inference.

## Directory Structure

```
llmserver/
├── llama-server.exe           # llama.cpp server binary (CUDA 12.4)
├── ggml-cuda.dll             # CUDA acceleration library
├── models/                    # Model cache directory
│   └── models/               # Downloaded models
│       └── Qwen--Qwen2.5-7B-Instruct-GGUF/
│           └── snapshots/master/
│               ├── qwen2.5-7b-instruct-fp16-00001-of-00004.gguf
│               ├── qwen2.5-7b-instruct-fp16-00002-of-00004.gguf
│               ├── qwen2.5-7b-instruct-fp16-00003-of-00004.gguf
│               └── qwen2.5-7b-instruct-fp16-00004-of-00004.gguf
├── start-llama-server.bat     # Windows startup script
└── README.md                   # This file
```

## Quick Start

### Option 1: Automatic (Recommended)
The AICSS backend will automatically start llama-server when needed.

### Option 2: Manual Start
Double-click `start-llama-server.bat` or run from command line:
```cmd
cd backend\llmserver
start-llama-server.bat
```

### Option 3: Custom Model
```cmd
cd backend\llmserver
start-llama-server.bat path\to\your\model.gguf
```

## Model Information

- **Model**: Qwen2.5-7B-Instruct (FP16 quantization)
- **Size**: ~14GB (4 split files)
- **VRAM Required**: ~16GB GPU recommended
- **Context Length**: 4096 tokens (default)
- **GPU Layers**: 35 (set for 16GB VRAM)

## Configuration

To modify server settings, edit `start-llama-server.bat` or `llama_server_manager.py`.

### Environment Variables
- `AICSS_LLM_BASE_URL` - LLM server URL (default: http://localhost:8080/v1)
- `AICSS_LLM_MODEL` - Model name

## Troubleshooting

### Server won't start / Out of memory
Reduce context size and GPU layers in the startup script:
```cmd
set CONTEXT_SIZE=2048
set GPU_LAYERS=20
```

### CUDA not detected
Make sure NVIDIA drivers and CUDA Toolkit 12.x are installed.

### Connection refused
Make sure llama-server is running before starting the backend.
Check with: `netstat -an | findstr 8080`

## Download More Models

To add a smaller quantized model (Q4_K_M ~5GB, fits easily in 8GB VRAM):

```bash
pip install huggingface_hub
python -c "
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    'Qwen/Qwen2.5-7B-Instruct-GGUF',
    'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf',
    local_dir='./models'
)
print(f'Downloaded: {path}')
"
```
