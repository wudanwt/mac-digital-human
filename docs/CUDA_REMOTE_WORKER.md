# CUDA Remote Worker

CUDA Worker is an additive backend for the existing distributed Worker pool. Apple-Silicon Macs continue to use `MuseTalkMLXEngine`; Linux NVIDIA nodes use the official MuseTalk 1.5 PyTorch/CUDA runtime. The Center, lease protocol, object-store transfer protocol and final composition contract stay shared.

## Design boundary

```text
RemotePageWorker
  -> create_musetalk_engine()
       -> mlx  -> MuseTalkMLXEngine      # existing Mac path
       -> cuda -> MuseTalkCUDAEngine     # Linux NVIDIA path
```

The default backend remains `mlx`. A CUDA node must explicitly set:

```env
REMOTE_WORKER_RENDER_BACKEND=cuda
REMOTE_WORKER_MODEL_VERSION=musetalk-cuda
```

This avoids changing existing Mac worker behavior.

## Network requirements

The CUDA machine only needs outbound HTTPS access to the Center and, when direct transfer is enabled, the private object-store signed URLs. The Center never connects inbound to the Worker. No public IP, PostgreSQL port, Redis port, or inbound Worker port is required.

## First install

Target: Ubuntu/Linux + NVIDIA driver + `nvidia-smi` and a bootstrap Python with `pip`.

```bash
git clone https://github.com/wudanwt/mac-digital-human-saas.git
cd mac-digital-human-saas
git checkout feat/cuda-worker

bash scripts/cloud/setup_musetalk_cuda.sh
bash scripts/cloud/setup_cuda_worker_runtime.sh
```

The CUDA deployment intentionally uses two isolated environments:

- `musetalk-cuda`: Python 3.10 + official MuseTalk 1.5 / PyTorch 2.0.1 CUDA 11.8.
- `digital-human-worker`: Python 3.11 + SaaS Worker / CosyVoice / matting / CUDA-enabled PyTorch 2.3.1.

The bootstrap prints the exact `CUDA_WORKER_PYTHON=...` path to copy into `.env.cuda-worker`.

`MuseTalkCUDAEngine` intentionally invokes the official MuseTalk runtime in the isolated Python 3.10 venv. CosyVoice runs in the main Worker process and automatically selects CUDA when that process sees `torch.cuda.is_available() == True`.

## Configure

On Center:

```bash
python -m app.saas.manage create-worker --name cuda-worker-01 --slots 1
```

Copy the returned `wrk_...` token to the CUDA machine:

```bash
cp .env.cuda-worker.example .env.cuda-worker
```

Edit at least:

```env
REMOTE_WORKER_API_BASE=https://worker-api.example.com/api/saas/internal/render
REMOTE_WORKER_TOKEN=wrk_...
REMOTE_WORKER_NAME=cuda-worker-01
```

If the Center uses a hard model gate, allow both backends:

```env
SAAS_DISTRIBUTED_EXPECTED_MODEL_VERSION=musetalk-mlx,musetalk-cuda
```

A single value remains valid, so existing Mac-only deployments do not change.

## Start

```bash
bash scripts/saas/start_remote_page_worker_cuda.sh
```

The startup script verifies the official MuseTalk CUDA environment and also requires CUDA to be visible in the main Worker Python so TTS does not silently fall back to CPU.

## Current CUDA behavior

- MuseTalk: official MuseTalk 1.5 PyTorch/CUDA implementation.
- TTS: existing CosyVoice 2.0 provider; it selects CUDA automatically when available.
- Page lease / heartbeat / downloads / uploads: same protocol as Mac Remote Worker.
- Portrait matting / transparent composition: same Worker code path.
- MuseTalk MLX resident runtime and Apple cache tuning are untouched.
- CUDA MuseTalk initially uses the official per-page inference entrypoint. Further resident-model/cache optimization can be added behind the CUDA backend without changing the Mac implementation.

## Production rollout

Start with one CUDA node and keep the existing Mac nodes online. Confirm:

1. Mac nodes still register as `backend:mlx`.
2. CUDA node registers as `backend:cuda`.
3. A CUDA node completes TTS + MuseTalk + compose for a real page.
4. Direct object-store download/upload succeeds or falls back to Center proxy.
5. Draining the CUDA node leaves Mac workers able to continue processing tasks.
