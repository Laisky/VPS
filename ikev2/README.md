# ikev2

just run

```sh
docker run -itd --privileged -v /lib/modules:/lib/modules --dns=8.8.8.8  -e HOSTIP='vpn.laisky.com' -e VPNUSER=laisky -e VPNPASS="12345678" -p 500:500/udp -p 4500:4500/udp --name=ikev2-vpn hanyifeng/alpine-ikev2-vpn
```

generate cert:

```sh
docker exec -it ikev2-vpn sh /usr/bin/vpn
```
