# Port forwarding over websocket with K8s demo

## Cluster setup

```bash
docker build kptunnel-docker -t kptunnel
docker run --rm kptunnel cat /kptunnel > kptunnel
chmod +x kptunnel
kind create cluster --config kind-conf.yaml
kind load docker-image kptunnel
kubectl create -f nginx.yaml
```

## Forward tunnel test

```bash
$ kubectl create -f forward-test-nginx.yaml
pod/test-nginx created
service/test-nginx created
$ python mktunnel.py -L :8888:test-nginx.default.svc.cluster.local:80
2023-09-30 20:12:51,896 [mktunnel.py:81] starting tunnel server
2023-09-30 20:12:52,069 [mktunnel.py:83] waiting for tunnel server ready
2023-09-30 20:12:52,932 [mktunnel.py:169] ws url: ws://localhost/ws-qzdebrfloclaxfil
2023-09-30 20:12:52,932 [mktunnel.py:172] listening on :8888
2023-09-30 20:12:52,933 [mktunnel.py:174] kptunnel log -> /tmp/kptunnel-rbbxjsdl.log
2023-09-30 20:12:52,933 [mktunnel.py:175] Press [Ctrl+C] to stop tunneling
```

```bash
$ curl http://localhost:8888
<!DOCTYPE html>
<html>
<head>
<title>Welcome to nginx!</title>
<style>
html { color-scheme: light dark; }
body { width: 35em; margin: 0 auto;
font-family: Tahoma, Verdana, Arial, sans-serif; }
</style>
</head>
<body>
<h1>Welcome to nginx!</h1>
<p>If you see this page, the nginx web server is successfully installed and
working. Further configuration is required.</p>

<p>For online documentation and support please refer to
<a href="http://nginx.org/">nginx.org</a>.<br/>
Commercial support is available at
<a href="http://nginx.com/">nginx.com</a>.</p>

<p><em>Thank you for using nginx.</em></p>
</body>
</html>
```

## Reverse tunnel test

```bash
$ docker run --rm -d -p 3333:80 httpd
$ python mktunnel.py -R localhost:3333
2023-09-30 20:08:39,383 [mktunnel.py:81] starting tunnel server
2023-09-30 20:08:39,572 [mktunnel.py:83] waiting for tunnel server ready
2023-09-30 20:08:40,194 [mktunnel.py:171] ws url: ws://localhost/ws-nmjmiqalrjhysjzj
2023-09-30 20:08:40,289 [mktunnel.py:174] listening on 172.18.0.2:30706
2023-09-30 20:08:40,290 [mktunnel.py:175] Press [Ctrl+C] to stop tunneling
2023-09-30 20:08:40,290 [mktunnel.py:98] kptunnel log -> /tmp/kptunnel-8lfrj7sb.log
```

```bash
$ kubectl run --image=curlimages/curl --restart=Never test-curl -- curl -s http://172.18.0.2:30706
pod/test-curl created
$ kubectl logs test-curl
<html><body><h1>It works!</h1></body></html>
$ kubectl delete pod test-curl
pod "test-curl" deleted
```
