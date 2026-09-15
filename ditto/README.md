# Ditto local lab

From the repository root, run:

```bash
cp ditto/nginx.htpasswd.example ditto/nginx.htpasswd
cd ditto
docker compose up -d
```

Demo account: `ditto/ditto`. Ports 8080, 8081, 27017 must be free. Do not start a second stack over the existing running stack. Tested runtime image digests are saved in results/report/docker_images.json.

For the exact tested runtime images: `docker compose -f docker-compose.yml -f docker-compose.tested.yml up -d`. The base defaults to Ditto 3.9.1. All nginx/static/profile-docs bind mounts are included locally; no mount points refer outside this repository. Swagger/OpenAPI documentation is excluded from this core repository; `/apidoc/` is disabled.

## Upstream attribution

`static/images/`, `static/wot/`, the landing page, and the base nginx/Compose files originate from Eclipse Ditto. The 74 retained static assets were compared byte-for-byte with the official **3.9.1** source release: all match. Verification and SHA-256 values are in `../results/report/ditto_asset_provenance.json`. They were copied from the local upstream source tree used by the running Docker deployment, rather than extracted from a Docker image.

Source: https://github.com/eclipse-ditto/ditto/tree/3.9.1. Upstream material is provided under EPL-2.0; copies of its license and notices are in `upstream/`. These files preserve the upstream attribution; no new license has been selected for the original DT4N code. The optional OpenAPI/Swagger files have been removed from the current Git tree; the earlier commit still contains them.
