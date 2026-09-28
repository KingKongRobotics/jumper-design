# Contributing

Contributions to Design Workflow should make the package behavior, supported inputs, and acceptance limits clear to users.

## Set up

```sh
git lfs install
git clone https://github.com/KingKongRobotics/kingkong-design.git
cd kingkong-design
git lfs pull
python -m pip install -e ".[sim,dev]"
```

## Before submitting

- Keep package format changes consistent across the schema, Python reference implementation, tests, and [content package protocol](docs/content-packages.md). Changes to required semantics need an explicit protocol version decision.
- Preserve package asset bytes and attribution. Do not change a manifest hash to mask changed content.
- Explain what a check establishes. Package structure, native MuJoCo loading, visual acceptance, and physical fit are distinct results.
- Update the relevant documentation and add or adjust focused tests for behavioral changes.

Run the repository checks from its root:

```sh
python -m pytest
python scripts/check_english.py
python scripts/check_publish.py
```

The checks above are suggested local commands; their presence here does not imply that they have been run for any particular change. Binary assets stored with Git LFS must be fetched to validate their actual contents.

## Licensing

By submitting a contribution, you agree that your contribution is offered under Apache-2.0 as described in [LICENSE](LICENSE). Include attribution and applicable license information for third-party material. See [licensing details](docs/licensing.md).
