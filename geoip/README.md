`GeoLite2-City.mmdb` belongs in this directory — it's licensed, so it's
gitignored and never committed. Requires a free MaxMind account:
https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

Two ways to get it there:

**Manual** — download the "GeoIP2 Binary (.mmdb)" tarball from the MaxMind
account portal, extract, and drop the `.mmdb` here.

**Automated (what the deployment uses)** — generate a license key, then
configure `geoipupdate`:

```
# /etc/GeoIP.conf, chmod 600, root-owned
AccountID <your-account-id>
LicenseKey <your-license-key>
EditionIDs GeoLite2-City
DatabaseDirectory /path/to/this/geoip/dir
```

`sudo geoipupdate` fetches it. A weekly cron keeps it current — see
`/etc/cron.weekly/geoipupdate-velocity` on the deployed box. That job also
restarts the load balancer, because `geoip.py` caches the `Reader` for the
process lifetime and won't notice a new file on disk otherwise.

Without this file, the Load Balancer's `/fetch` endpoint still works — it
falls back to Origin's home region for any request that doesn't pass an
explicit `?region=` override, and logs `resolution_method=geoip_unresolved`.
