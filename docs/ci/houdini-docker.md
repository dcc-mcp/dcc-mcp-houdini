# Houdini Docker E2E

`dcc-mcp-houdini` keeps live Houdini coverage in a separate `E2E (Houdini)`
workflow because Houdini containers require SideFX licensing credentials.

## Candidate Images

| Image | Source | Notes |
|-------|--------|-------|
| `sabjorn/hbuild-worker:21.0.559-base` | <https://hub.docker.com/r/sabjorn/hbuild-worker> | Based on `aaronsmithtv/hbuild`; advertises `python` with access to `hou`, HDA-oriented CI usage, and SideFX credential environment variables. This is the default image in `.github/workflows/e2e.yml`. |
| `aaronsmithtv/hbuild:latest` | <https://github.com/aaronsmithtv/Houdini-Docker> | MIT-licensed workflow for building/publishing Houdini production-build images. The README documents `hython` availability after license setup and notes the images are governed by SideFX EULA terms. |
| SideFX daily-build Dockerfile | <https://www.sidefx.com/download/daily-builds/?production=true&docker=true> | Official build-your-own path referenced by SideFX forum users; useful when a studio wants to pin an internal image instead of pulling public Docker Hub images. |

## Required Repository Configuration

Set these repository secrets to enable live E2E:

- `SIDEFX_CLIENT`
- `SIDEFX_SECRET`
- `HOUDINI_USERNAME` (optional for images that need account login)
- `HOUDINI_PASSWORD` (optional for images that need account login)

Optional repository variables:

- `HOUDINI_IMAGE`, default `sabjorn/hbuild-worker:21.0.559-base`
- `HOUDINI_LICENSE_MODE`, default `indie`

When `SIDEFX_CLIENT` or `SIDEFX_SECRET` is missing, the workflow explains the
skip and exits successfully. Unit tests, skill lint, package build, and
quickinstall assembly remain mandatory in `CI`.
