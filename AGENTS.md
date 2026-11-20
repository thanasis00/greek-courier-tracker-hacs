# Working on Greek Courier Tracker

## Before every commit

1. Run the tests: `make test-unit` (Docker).
2. Run the visual test of the dashboard card: `make visual`.
   - It renders the card in every scenario of `tests/visual/scenarios.js` (each
     stage and problem, special rows, expanded rows, owners, history, empty
     card; Greek and English; light and dark; normal and narrow width) into
     `tests/visual/snapshots/current/` and compares them with the images of the
     last release.
   - Open `tests/visual/report/index.html`: changed images are shown side by
     side with a diff (changes in red).
   - Every change must be one the commit means to make. Fix unintended ones
     before committing, and tell the user which scenarios changed and why.
   - When the card learns to show something new, add a row or a scenario to
     `tests/visual/scenarios.js` in the same commit.

## Before every release

1. Bump `version` in `custom_components/greek_courier_tracker/manifest.json`
   (its own commit, "Bump version to X.Y.Z").
2. Run the tests again, and hassfest:
   `docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest`
   (CI runs it too; it is not part of the unit tests).
3. Run `make visual-release`. It keeps the images of the new version in
   `tests/visual/snapshots/<version>/`, compares them with the previous release
   and keeps only the last 3 releases. Review the report as above, and mention
   visible card changes in the release notes.
4. Then push, tag and publish the release.

## Notes

- `tests/visual/snapshots/` and `tests/visual/report/` are in `.gitignore`:
  the images stay on this machine. Without images of an earlier release, the
  run says "Compared with: nothing" and every image is new.
- The visual test runs in the Docker image of `tests/visual/Dockerfile`
  (Playwright with Chromium), with the clock fixed at 20/11/2026 12:00 Athens
  time, so two runs of the same code give the same images.
