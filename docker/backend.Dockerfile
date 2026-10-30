# 筆電重型最佳化映像（草稿）：slam/backend。SLAM 系統選定後補齊。
# 建議與 ROS 2 發行版對應的映像（見 ADR 0003）
ARG BASE_IMAGE=TODO
FROM ${BASE_IMAGE}

ARG GIT_COMMIT=unknown
ARG GIT_DESCRIBE=unknown
ENV DSN_ROLE=backend \
    DSN_GIT_COMMIT=${GIT_COMMIT} \
    DSN_GIT_DESCRIBE=${GIT_DESCRIBE} \
    PYTHONUNBUFFERED=1

WORKDIR /opt/dsn
COPY requirements/ requirements/
RUN python3 -m pip install --no-cache-dir -r requirements/backend.txt

COPY common/ common/
COPY slam/ slam/
COPY config/ config/
COPY calibration/ calibration/
COPY scripts/env_check.py scripts/env_check.py
