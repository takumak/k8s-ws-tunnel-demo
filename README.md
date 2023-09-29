# Port forwarding over websocket with K8s demo

```bash
docker build kptunnel-docker -t kptunnel
docker run --rm kptunnel cat /kptunnel > kptunnel
chmod +x kptunnel
kind create cluster --config kind-conf.yaml
kind load docker-image kptunnel
kubectl create -f nginx.yaml
kubectl create -f test.yaml
python mktunnel.py -L :8888:test-nginx.default.svc.cluster.local:80 &
curl http://localhost:8888
```
