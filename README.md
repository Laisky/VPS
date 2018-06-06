# docker-compose for my VPS


Prepare configs:

```sh
git clone git@gitlab.com:Laisky/configs.git /opt/config
```

Run:

```
docker-compose build
docker-compose up -d --remove-orphans --force-recreate
```


## TODO

- [x] mongodb
- [ ] fluentd
- [ ] blog
- [x] shadowsocks
- [x] shadowsocksr
- [ ] v2ray
- [ ] ramjet
- [ ] nginx
- [x] rocket.chat
