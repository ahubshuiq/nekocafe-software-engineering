# NekoCafé 回滚手册

## Docker Compose 环境回滚

### 查看当前运行版本
```bash
docker compose ps
docker images nekocafe/reservation
```

### 回滚操作
```bash
docker compose down
# 修改 docker-compose.yml 中的镜像 tag 为目标版本
docker compose up -d
```

## Helm / K8s 环境回滚

### 查看发布历史
```bash
helm history nekocafe -n nekocafe-prod
```

### 回滚到上一版本
```bash
helm rollback nekocafe 0 -n nekocafe-prod --wait --timeout 5m
```

### 回滚到指定版本
```bash
helm rollback nekocafe <revision> -n nekocafe-prod --wait --timeout 5m
```

### 回滚后验证
```bash
kubectl get pods -n nekocafe-prod
curl https://api.nekocafe.com/actuator/health
```
