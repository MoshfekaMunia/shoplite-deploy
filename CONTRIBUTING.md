# Contributing to ShopLite

## Branches

- `main` contains reviewed, demonstrable work.
- `develop` collects completed features.
- Create branches from `develop` using `feature/<short-name>`.

## Pull requests

1. Keep each pull request focused on one work area.
2. Explain what changed, how it was tested, and any known limitation.
3. Make sure CI passes before merging.
4. Merge into `develop`; promote `develop` to `main` for a release.

## Commit messages

Use Conventional Commits:

- `feat(user): add user creation endpoint`
- `fix(order): return quickly when catalog is unavailable`
- `test(compose): verify required service definitions`
- `docs(readme): add clean-machine setup`

Never commit `.env`, credentials, Terraform state, IDE files, or generated
artifacts.

