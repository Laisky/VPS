## Docker Images

### EdgelessRT

```sh
docker build ./ego --target release_develop -f ego/edgelessrt.Dockerfile -t ppcelery/edgelessrt-dev:20221201
docker build ./ego --target release_deploy -f ego/edgelessrt.Dockerfile -t ppcelery/edgelessrt-deploy:20221201

docker push ppcelery/edgelessrt-dev:20221201
docker push ppcelery/edgelessrt-deploy:20221201
```

### Ego

```sh
docker build ./ego --target dev -f ego/ego.Dockerfile -t ppcelery/ego-dev:1.0.1-20221201
docker build ./ego --target deploy -f ego/ego.Dockerfile -t ppcelery/ego-deploy:1.0.1-20221201

docker push ppcelery/ego-dev:1.0.1-20221201
docker push ppcelery/ego-deploy:1.0.1-20221201

```
