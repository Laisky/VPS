## Docker Images

### EdgelessRT

```sh
db ./ego --target release_develop -f ego/edgelessrt.Dockerfile -t ppcelery/edgelessrt-dev:20221201
db ./ego --target release_deploy -f ego/edgelessrt.Dockerfile -t ppcelery/edgelessrt-deploy:20221201

docker push ppcelery/edgelessrt-dev:20221201
docker push ppcelery/edgelessrt-deploy:20221201
```

### Ego

```sh
db ./ego --target dev -f ego/ego.Dockerfile -t ppcelery/ego-dev:1.0.1-20221201
db ./ego --target deploy -f ego/ego.Dockerfile -t ppcelery/ego-deploy:1.0.1-20221201

docker push ppcelery/ego-dev:1.0.1-20221201
docker push ppcelery/ego-deploy:1.0.1-20221201

```
