# Ditto local lab

Copy `nginx.htpasswd.example` to `nginx.htpasswd` (demo account ditto/ditto), then `docker compose up -d` from this directory. Ports 8080, 8081, 27017 must be free. Do not start a second stack over the existing running stack. Tested runtime image digests are saved in results/report/docker_images.json.

For the exact tested runtime images: `docker compose -f docker-compose.yml -f docker-compose.tested.yml up -d`. The base defaults to Ditto 3.9.1. All nginx/static/profile-docs bind mounts are included locally; no mount points refer outside this repository. Optional Swagger uses `--profile docs`; it was not part of live acceptance.
