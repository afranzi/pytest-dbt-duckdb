# PyTest dbt Duckdb

A library for fearless analytics engineering, built for CI/CD integration.

!!! info "What is this?"
    E2E dbt Testing with DuckDB is a Python library designed to validate your dbt models end-to-end, running locally on
    DuckDB for fast, cost-efficient testing. Seamlessly integrate it into your CI/CD pipelines and catch errors before they catch you.

## 🔍 Why This Exists

!!! danger "Assumptions are dangerous."
    An untested model is a ticking time bomb—silent, unseen, but waiting to fail at the worst possible moment.
    This library ensures your transformations, dependencies, and outputs are battle-tested before deployment.

## 💡 Data must be tested, not trusted.

Modern data teams ship thousands of transformations, yet most rely on post-mortem debugging instead of proactive validation. This stops today.

With DuckDB as the testing engine, you can:

- [x] Define and validate data scenarios before deployment.
- [x] Run ultra-fast local tests without expensive cloud queries.
- [x] Embed dbt testing directly into CI/CD pipelines.

Test fearlessly. Deploy confidently.

## 🚀 How It Works

- :one: Define Your Tests
Write E2E validation scenarios in YAML, specifying inputs, transformations, and expected outputs.

- :two: Run with DuckDB
Execute tests locally—without the cost or delay of running queries in production.

- :three: Integrate with CI/CD
Embed tests into GitHub Actions, Jenkins, GitLab CI/CD, or any automation pipeline.

- :four: Ship Data You Trust
Prevent bad models before they hit production.

## 🎬 Join the Journey
Data engineering is not just about moving bytes. It’s about storytelling, precision, and trust.
This library is your watchtower, ensuring every model tells the right story—before it ever reaches an audience.

!!! quote
    "A model untested is a story unfinished."
