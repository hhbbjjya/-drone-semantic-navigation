# 機載 Orin Nano 映像（草稿）。在 Jetson 上建置：
#   docker build -f docker/onboard.Dockerfile \
#     --build-arg L4T_TAG=<與 /etc/nv_tegra_release 相符的標籤> \
#     --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
#     --build-arg GIT_DESCRIBE=$(git describe --always --tags --dirty) \
#     -t dsn/onboard .
# 基底映像的 L4T 版本必須與實機 JetPack 相符，否則 CUDA 無法使用。
ARG L4T_TAG=TODO
FROM nvcr.io/nvidia/l4t-jetpack:${L4T_TAG}

ARG GIT_COMMIT=unknown
ARG GIT_DESCRIBE=unknown
ENV DSN_ROLE=onboard \
    DSN_GIT_COMMIT=${GIT_COMMIT} \
    DSN_GIT_DESCRIBE=${GIT_DESCRIBE} \
    PYTHONUNBUFFERED=1

WORKDIR /opt/dsn
COPY requirements/ requirements/
RUN python3 -m pip install --no-cache-dir -r requirements/jetson.txt
# TODO: ROS 2（發行版依 ADR 0003）

COPY common/ common/
COPY onboard/ onboard/
# SLAM 前端與共用資料結構（slam/frontend、slam/core）
COPY slam/ slam/
COPY config/ config/
COPY calibration/ calibration/
COPY scripts/env_check.py scripts/env_check.py
