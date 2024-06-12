<https://docs.liteseed.xyz/operators/running-a-node>

```sh
git clone https://github.com/liteseed/edge

cd ./edge
db -t ppcelery/liteseed-edge:latest .
docker push ppcelery/liteseed-edge:latest


# --------------------------------------------------
# ⚠️⚠️⚠️ DANGEROUS ⚠️⚠️⚠️
#
# this generates a new wallet with a new private key
# --------------------------------------------------
docker run -id --rm -v /var/lib/liteseed:/data ppcelery/liteseed-edge:latest generate
# --------------------------------------------------

docker run -id --rm  -v /var/lib/liteseed:/data ppcelery/liteseed-edge:latest migrate
docker run -id --rm -v /var/lib/liteseed:/data ppcelery/liteseed-edge:latest balance
```
