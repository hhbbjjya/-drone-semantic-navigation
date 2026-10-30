# 桌機 VLM 映像（草稿）。模型權重不打包進映像，執行時掛載 DSN_DATA_ROOT 與 HF 快取。
#   docker build -f docker/vlm.Dockerfile \
#     --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
#     --build-arg GIT_DESCRIBE=$(git describe --always --tags --dirty) -t dsn/vlm .
#   docker run --gpus all -v $DSN_DATA_ROOT:/data -v ~/.cache/huggingface:/root/.cache/huggingface dsn/vlm
# 選支援 Blackwell（CUDA 12.8 以上）的 runtime 映像
ARG CUDA_IMAGE=TODO
FROM ${CUDA_IMAGE}

ARG GIT_COMMIT=unknown
ARG GIT_DESCRIBE=unknown
# 對應 CUDA 版本的 PyTorch wheel index
ARG TORCH_INDEX_URL=TODO
ENV DSN_ROLE=vlm \
    DSN_GIT_COMMIT=${GIT_COMMIT} \
    DSN_GIT_DESCRIBE=${GIT_DESCRIBE} \
    DSN_DATA_ROOT=/data \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/dsn
COPY requirements/ requirements/
RUN python3 -m pip install --no-cache-dir torch torchvision --index-url ${TORCH_INDEX_URL} \
 && python3 -m pip install --no-cache-dir -r requirements/desktop-vlm.txt

COPY common/ common/
COPY roomscan/ roomscan/
COPY config/ config/
COPY scripts/env_check.py scripts/env_check.py
